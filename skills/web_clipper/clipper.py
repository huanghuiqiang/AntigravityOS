"""
clipper.py
──────────────────────────────────────────────────────────────────
Antigravity OS  |  Web Clipper Skill

职责：
  接受一个 URL → 提取正文 → Bouncer LLM 评分 → 写入 Obsidian Inbox

特点（区别于 cognitive_bouncer 的 cron 模式）：
  - 即时触发：不需要等 08:00 cron
  - 单文章精读：用 trafilatura 做高质量正文提取（vs bouncer 的 <p> 抓取）
  - 无论高低分都推送 Telegram 告知结果
  - 低分文章只通知，不写 Inbox（避免垃圾入库）

触发方式：
  1. CLI:      PYTHONPATH=. python skills/web_clipper/clipper.py "https://..."
  2. Pi/Telegram 指令配置后：对 Pi 说 "clip https://..."
  3. import:  from skills.web_clipper.clipper import clip_url

依赖：
  pip install trafilatura httpx pyyaml python-dotenv requests
"""

import re
import json
import argparse
import requests
import httpx
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── 导入内部工具 ──────────────────────────────────────────────────
from agos.config import inbox_path, min_score_threshold, model_bouncer, openrouter_api_key
from agos.notify import send_message

# ── 配置 ──────────────────────────────────────────────────────────
MIN_SCORE_INBOX = min_score_threshold()  # 低于此分只通知，不写 Inbox
OPENROUTER_KEY = openrouter_api_key()
MODEL = model_bouncer()
INBOX_DIR = inbox_path()

# ── 正文提取 ──────────────────────────────────────────────────────

def extract_content(url: str) -> dict:
    """
    用 trafilatura 提取高质量正文。
    回退链：trafilatura → BeautifulSoup <p> → 空字符串

    Returns: { "title": str, "text": str, "author": str, "date": str }
    """
    # 优先用 trafilatura（工业级 readability）
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            result = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                output_format="json",
            )
            if result:
                data = json.loads(result)
                return {
                    "title":  data.get("title", ""),
                    "text":   (data.get("text", "") or "")[:6000],
                    "author": data.get("author", ""),
                    "date":   data.get("date", ""),
                }
    except Exception as e:
        print(f"  [trafilatura 失败，降级]: {e}")

    # 回退：BeautifulSoup 抓 <p> 段落
    try:
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AntigravityClipper/1.0)"}
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                soup  = BeautifulSoup(resp.content, "html.parser")
                title = soup.title.string if soup.title else ""
                paras = " ".join(p.get_text() for p in soup.find_all("p"))
                return {"title": title, "text": paras[:6000], "author": "", "date": ""}
    except Exception as e:
        print(f"  [BeautifulSoup 回退失败]: {e}")

    return {"title": "", "text": "", "author": "", "date": ""}


# ── LLM 评分（复用 Bouncer 的 system prompt）────────────────────

SYSTEM_PROMPT = """
你是一个名叫 'Antigravity Bouncer' 的认知守门员。你的唯一职责是对抗信息熵增。
请阅读提交的文章摘要和片段，并评估其"认知摩擦（Friction）"和"系统2深度（System 2 Depth）"。

【高分标准 (8.0-10.0)】：
1. 具有强烈的"反共识"或颠覆传统的极客/工程视角。
2. 能提炼出具有复利价值的"公理（Axiom）"或架构思想。
3. 能够指导程序员去"造本能"，而不是"找轮子"。

【低分垃圾 (0.0-7.9)】：
1. 蹭热点的水文、情绪宣泄。
2. 无脑搬运的新闻通稿、常识废话、"如何安装Python"等基础教程。
3. 软广或标题党。

请严格返回合法的 JSON 对象，包含以下字段：
{"score": 数字(0-10), "reason": "极简的一句话解释是否有技术价值", "axiom_extracted": "提取的底层公理(低分可留空)"}
确保除了上述 JSON 外不输出任何多余的 Markdown 标记或其他文本。
"""


def evaluate(title: str, text: str) -> Optional[dict]:
    """
    调用 Gemini Flash 评分。
    Returns: {"score": float, "reason": str, "axiom_extracted": str} or None
    """
    if not OPENROUTER_KEY:
        print("  ❌ 未找到 OPENROUTER_API_KEY（兼容 GEMINI_API_KEY）")
        return None

    eval_text = f"Title: {title}\nBody Snippet:\n{text[:3000]}"

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization":  f"Bearer {OPENROUTER_KEY}",
                "Content-Type":   "application/json",
                "HTTP-Referer":   "https://github.com/huanghuiqiang/AntigravityOS",
                "X-Title":        "Antigravity Web Clipper",
            },
            json={
                "model":    MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": eval_text},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=30.0,
        )

        if resp.status_code != 200:
            print(f"  ❌ LLM 响应异常: HTTP {resp.status_code}")
            return None

        raw = resp.json()["choices"][0]["message"]["content"]
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(clean)

    except Exception as e:
        print(f"  ❌ LLM 评分出错: {e}")
        return None


# ── 写入 Obsidian Inbox ───────────────────────────────────────────

def write_to_inbox(
    url: str,
    title: str,
    score: float,
    reason: str,
    axiom: str,
    author: str = "",
    date: str = "",
) -> str:
    """
    将高分文章写入 Obsidian 00_Inbox，返回写入路径。
    frontmatter 含 status: pending，供 inbox_processor 消费。
    """
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:60].strip() or "Untitled"
    filename   = f"Clip - {safe_title}.md"
    filepath = INBOX_DIR / filename

    today = datetime.now().strftime("%Y-%m-%d")
    meta_author = f"\n**作者**: {author}" if author else ""
    meta_date   = f"\n**发布日期**: {date}" if date else ""

    content = f"""---
tags:
  - WebClip
score: {score}
status: pending
source: "{url}"
title: "{title.replace('"', "'")}"
created: "{today}"
---

# {title}

**来源链接**: [{url}]({url}){meta_author}{meta_date}
**认知得分**: {score}

> [!abstract] 核心公理 (Axiom)
> {axiom if axiom else "待提炼"}

> [!info] 守门员判决理由 (Reason)
> {reason}
"""

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")
    print(f"  📥 已写入 Inbox: {filename}")
    return str(filepath)


# ── Telegram 通知 ─────────────────────────────────────────────────

def notify(url: str, title: str, score: float, reason: str, axiom: str, written: bool):
    """推送评分结果到 Telegram。"""
    if score >= 9.5:   medal = "💎"
    elif score >= 9.0: medal = "🏆"
    elif score >= 8.5: medal = "🥇"
    elif score >= 8.0: medal = "⭐️"
    else:              medal = "🗑️"

    inbox_line = "📥 已写入 Obsidian Inbox（status: pending）" if written else "❌ 低分，未入库"

    text = (
        f"✂️ <b>Web Clipper 结果</b>\n\n"
        f"{medal} 得分：<b>{score:.1f}</b>\n"
        f"📰 <a href=\"{url}\">{title or url}</a>\n\n"
        f"🧠 <i>{axiom or '无公理'}</i>\n\n"
        f"💬 {reason}\n\n"
        f"{inbox_line}"
    )
    send_message(text)


# ── 主入口 ────────────────────────────────────────────────────────

def clip_url(url: str, silent: bool = False) -> dict:
    """
    完整 Clip 流程：提取 → 评分 → 写 Inbox → 通知

    Args:
        url:    目标网页 URL
        silent: True 时不推送 Telegram（适合批量调用）

    Returns:
        {
            "url": str, "title": str,
            "score": float, "reason": str, "axiom": str,
            "written": bool,   # 是否写入了 Inbox
            "filepath": str,   # Inbox 文件路径（未写入则为空）
        }
    """
    print(f"\n✂️  [Web Clipper] 开始处理: {url}")

    # Step 1: 提取正文
    print("  📄 正在提取正文（trafilatura）...")
    extracted = extract_content(url)
    title  = extracted["title"] or url
    text   = extracted["text"]
    author = extracted["author"]
    date   = extracted["date"]

    if not text:
        print("  ⚠️  正文为空，仅凭 URL 评分（准确度降低）")

    # 标题 fallback：从 URL path 提取可读名称
    if not title or title == url:
        from urllib.parse import urlparse
        path  = urlparse(url).path.rstrip("/")
        slug  = path.split("/")[-1] if path else urlparse(url).netloc
        title = slug.replace("-", " ").replace("_", " ").title() or url

    print(f"  📌 标题: {title[:70]}")

    # Step 2: LLM 评分
    print(f"  🧠 提交给 Gemini 2.0 Flash 评分...")
    result = evaluate(title, text)

    if result is None:
        msg = "评分失败，跳过入库"
        print(f"  ❌ {msg}")
        if not silent:
            send_message(f"✂️ Web Clipper 评分失败\n🔗 {url}")
        return {"url": url, "title": title, "score": 0, "written": False, "filepath": ""}

    score  = float(result.get("score", 0))
    reason = result.get("reason", "")
    axiom  = result.get("axiom_extracted", "")

    print(f"  📊 得分: {score:.1f} | 理由: {reason[:60]}")

    # Step 3: 判定是否写入 Inbox
    written  = False
    filepath = ""

    if score >= MIN_SCORE_INBOX:
        print(f"  🏆 高价值内容，写入 Obsidian Inbox...")
        filepath = write_to_inbox(url, title, score, reason, axiom, author, date)
        written  = True
    else:
        print(f"  🗑️  低分内容（{score:.1f} < {MIN_SCORE_INBOX}），不入库")

    # Step 4: Telegram 通知
    if not silent:
        notify(url, title, score, reason, axiom, written)

    return {
        "url":      url,
        "title":    title,
        "score":    score,
        "reason":   reason,
        "axiom":    axiom,
        "written":  written,
        "filepath": filepath,
    }


# ── CLI ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Antigravity Web Clipper — 即时剪报并评分入库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python skills/web_clipper/clipper.py "https://example.com/article"
  python skills/web_clipper/clipper.py "https://..." --silent
  python skills/web_clipper/clipper.py "https://..." --min-score 7.0
        """,
    )
    parser.add_argument("url",        help="要剪报的网页 URL")
    parser.add_argument("--silent",   action="store_true", help="不推送 Telegram")
    parser.add_argument("--min-score", type=float, default=MIN_SCORE_INBOX,
                        help=f"入库门槛（默认 {MIN_SCORE_INBOX}）")
    args   = parser.parse_args()

    MIN_SCORE_INBOX = args.min_score
    result = clip_url(args.url, silent=args.silent)

    print("\n" + "=" * 50)
    print(f"✅ 完成")
    print(f"   得分:  {result['score']:.1f}")
    print(f"   入库:  {'是 → ' + result['filepath'] if result['written'] else '否'}")
    print("=" * 50)
