"""
pdf_ingester.py
──────────────────────────────────────────────────────────────────
Antigravity OS  |  PDF Ingester Skill

职责：
  接受 PDF 文件路径或 URL → 提取正文 → Bouncer LLM 评分 → 写入 Obsidian Inbox
"""

import re
import json
import argparse
import tempfile
import httpx
from pathlib import Path
from datetime import datetime
from typing import Optional

from agos.config import (
    openrouter_api_key, vault_path, inbox_folder,
    min_score_threshold, model_bouncer,
)
from agos.notify import send_message

from skills.obsidian_bridge.bridge import get_vault

# ── 配置 ─────────────────────────────────────────────────────────
OPENROUTER_KEY  = openrouter_api_key()
MODEL           = model_bouncer()
MIN_SCORE_INBOX = min_score_threshold()
INBOX_DIR       = vault_path() / inbox_folder()
MAX_CHARS       = 6000      # 提交给 LLM 的最大正文字符数


# ── Step 1: 获取 PDF（本地或远程）────────────────────────────────

def fetch_pdf(source: str) -> Optional[Path]:
    """返回 PDF 本地路径。"""
    src = source.strip()

    if src.startswith("http://") or src.startswith("https://"):
        print(f"  📥 下载 PDF: {src[:80]}...")
        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; AntigravityPDFIngester/1.0)"}
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                resp = client.get(src, headers=headers)
                resp.raise_for_status()

                suffix = ".pdf"
                tmp    = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tmp.write(resp.content)
                tmp.close()
                print(f"  ✅ 下载完成: {Path(tmp.name).name}")
                return Path(tmp.name)

        except Exception as e:
            print(f"  ❌ 下载失败: {e}")
            return None
    else:
        p = Path(src).expanduser()
        if not p.exists():
            print(f"  ❌ 文件不存在: {p}")
            return None
        return p


# ── Step 2: 提取正文 ──────────────────────────────────────────────

def extract_text(pdf_path: Path) -> dict:
    """提取 PDF 正文。"""
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            pages     = len(pdf.pages)
            all_text  = []
            for i, page in enumerate(pdf.pages[:20]):
                txt = page.extract_text()
                if txt:
                    all_text.append(txt.strip())
            full_text = "\n".join(all_text)
            title = ""
            if all_text:
                first_lines = all_text[0].split("\n")[:4]
                for line in first_lines:
                    line = line.strip()
                    if 5 < len(line) < 200 and not line.isdigit():
                        title = line
                        break
            return {
                "title": title or pdf_path.stem,
                "text":  full_text[:MAX_CHARS],
                "pages": pages,
            }
    except ImportError:
        pass

    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        pages  = len(reader.pages)
        texts  = []
        for page in reader.pages[:20]:
            t = page.extract_text()
            if t: texts.append(t)
        full_text = "\n".join(texts)
        return {
            "title": pdf_path.stem,
            "text":  full_text[:MAX_CHARS],
            "pages": pages,
        }
    except Exception as e:
        print(f"  ❌ 文本提取失败: {e}")
        return {"title": pdf_path.stem, "text": "", "pages": 0}


# ── Step 3: LLM 评分 ─────────────────────────────────────────────

SYSTEM_PROMPT = """
你是一个名叫 'Antigravity Bouncer' 的认知守门员。你的唯一职责是对抗信息熵增。
请阅读提交的 PDF 文档摘要，并评估其"认知摩擦（Friction）"和"系统2深度（System 2 Depth）"。

【高分标准 (8.0-10.0)】：
1. 具有强烈的"反共识"或颠覆传统的极客/工程视角。
2. 能提炼出具有复利价值的"公理（Axiom）"或架构思想。
3. 能够指导程序员去"造本能"，而不是"找轮子"。

【低分垃圾 (0.0-7.9)】：
1. 蹭热点的水文、情绪宣泄。
2. 无脑搬运的新闻通稿、常识废话。
3. 软广或标题党。

请严格返回合法的 JSON 对象：
{"score": 数字(0-10), "reason": "极简的一句话解释是否有技术价值", "axiom_extracted": "提取的底层公理(低分可留空)"}
不要输出任何额外文本或 Markdown 包裹。
"""

def evaluate(title: str, text: str, pages: int) -> Optional[dict]:
    if not OPENROUTER_KEY:
        print("  ❌ 未找到 API Key")
        return None

    eval_text = f"PDF 标题: {title}\n总页数: {pages}\n正文片段:\n{text[:3000]}"

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "Content-Type":  "application/json",
                    "HTTP-Referer":  "https://github.com/huanghuiqiang/AntigravityOS",
                    "X-Title":       "Antigravity PDF Ingester",
                },
                json={
                    "model":    MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": eval_text},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )

        if resp.status_code != 200:
            print(f"  ❌ LLM 响应异常: HTTP {resp.status_code}")
            return None

        raw   = resp.json()["choices"][0]["message"]["content"]
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(clean)

    except Exception as e:
        print(f"  ❌ LLM 评分出错: {e}")
        return None


# ── Step 4: 写入 Obsidian Inbox ───────────────────────────────────

def write_to_inbox(
    source: str,
    title: str,
    score: float,
    reason: str,
    axiom: str,
    pages: int,
) -> str:
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:60].strip() or "Untitled PDF"
    filename   = f"PDF - {safe_title}.md"
    filepath   = INBOX_DIR / filename
    today      = datetime.now().strftime("%Y-%m-%d")

    is_url = source.startswith("http")
    src_line = f"[{source}]({source})" if is_url else f"`{source}`"

    content = f"""---
tags:
  - PDFIngested
score: {score}
status: pending
source: "{source}"
title: "{title.replace('"', "'")}"
created: "{today}"
pages: {pages}
---

# {title}

**来源**: {src_line}
**总页数**: {pages}
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


# ── Step 5: Telegram 通知 ─────────────────────────────────────────

def notify(source: str, title: str, score: float, reason: str, axiom: str,
           pages: int, written: bool):
    if score >= 9.5:   medal = "💎"
    elif score >= 9.0: medal = "🏆"
    elif score >= 8.5: medal = "🥇"
    elif score >= 8.0: medal = "⭐️"
    else:              medal = "🗑️"

    inbox_line = "📥 已写入 Obsidian Inbox" if written else "❌ 低分，未入库"
    src_label  = title or Path(source).name

    text = (
        f"📄 <b>PDF Ingester 结果</b>\n\n"
        f"{medal} 得分：<b>{score:.1f}</b>\n"
        f"📚 {src_label}（{pages} 页）\n\n"
        f"🧠 <i>{axiom or '无公理'}</i>\n\n"
        f"💬 {reason}\n\n"
        f"{inbox_line}"
    )
    send_message(text)


# ── 主入口 ────────────────────────────────────────────────────────

def ingest_pdf(source: str, silent: bool = False) -> dict:
    """完整 PDF 处理流程。"""
    print(f"\n📄 [PDF Ingester] 开始处理: {source[:80]}")

    pdf_path = fetch_pdf(source)
    if not pdf_path:
        return {"source": source, "title": "", "score": 0, "written": False, "pages": 0}

    is_temp = source.startswith("http")

    try:
        extracted = extract_text(pdf_path)
        title     = extracted["title"]
        text      = extracted["text"]
        pages     = extracted["pages"]

        if not text:
            print("  ⚠️  正文为空，跳过评分")
            return {"source": source, "title": title, "score": 0, "written": False, "pages": pages}

        result = evaluate(title, text, pages)
        if result is None:
            return {"source": source, "title": title, "score": 0, "written": False, "pages": pages}

        score  = float(result.get("score", 0))
        reason = result.get("reason", "")
        axiom  = result.get("axiom_extracted", "")

        written  = False
        filepath = ""
        if score >= MIN_SCORE_INBOX:
            filepath = write_to_inbox(source, title, score, reason, axiom, pages)
            written  = True

        if not silent:
            notify(source, title, score, reason, axiom, pages, written)

        return {"source": source, "title": title, "score": score,
                "reason": reason, "axiom": axiom,
                "written": written, "filepath": filepath, "pages": pages}

    finally:
        if is_temp and pdf_path and pdf_path.exists():
            pdf_path.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Antigravity PDF Ingester")
    parser.add_argument("source",      help="PDF 文件路径或 URL")
    parser.add_argument("--silent",    action="store_true")
    parser.add_argument("--min-score", type=float, default=MIN_SCORE_INBOX)
    args = parser.parse_args()

    MIN_SCORE_INBOX = args.min_score
    ingest_pdf(args.source, silent=args.silent)
