"""
pdf_ingester.py
──────────────────────────────────────────────────────────────────
Antigravity OS  |  PDF Ingester Skill

职责：
  接受 PDF 文件路径或 URL → 提取正文 → Bouncer LLM 评分 → 写入 Obsidian Inbox

支持来源：
  - 本地文件：/path/to/paper.pdf
  - 远程 URL：https://arxiv.org/pdf/xxxx.pdf

触发方式：
  1. CLI:    PYTHONPATH=. python skills/global_tools/pdf_ingester/pdf_ingester.py /path/to/file.pdf
  2. import: from skills.global_tools.pdf_ingester.pdf_ingester import ingest_pdf

依赖（已安装）：
  pdfplumber, requests, python-dotenv
"""

import os
import re
import sys
import json
import argparse
import tempfile
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── 路径初始化 ────────────────────────────────────────────────────
_THIS_DIR = Path(__file__).parent
_ROOT     = _THIS_DIR.parent.parent.parent       # Antigravity root
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / "agents/cognitive_bouncer/.env")

from skills.obsidian_bridge.bridge import get_vault

_BOUNCER_DIR = _ROOT / "agents/cognitive_bouncer"
sys.path.insert(0, str(_BOUNCER_DIR))
from telegram_notify import send_message

# ── 配置 ─────────────────────────────────────────────────────────
OPENROUTER_KEY  = os.getenv("GEMINI_API_KEY", "")
MODEL           = "google/gemini-2.0-flash-001"
MIN_SCORE_INBOX = float(os.getenv("PDF_MIN_SCORE", "8.0"))
INBOX_DIR       = str(get_vault() / "00_Inbox")
MAX_CHARS       = 6000      # 提交给 LLM 的最大正文字符数


# ── Step 1: 获取 PDF（本地或远程）────────────────────────────────

def fetch_pdf(source: str) -> Optional[Path]:
    """
    返回 PDF 本地路径。
    - 本地路径 → 直接返回
    - URL      → 下载到临时文件后返回
    """
    src = source.strip()

    if src.startswith("http://") or src.startswith("https://"):
        print(f"  📥 下载 PDF: {src[:80]}...")
        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; AntigravityPDFIngester/1.0)"}
            resp    = requests.get(src, headers=headers, timeout=30, stream=True)
            resp.raise_for_status()

            suffix = ".pdf"
            tmp    = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            for chunk in resp.iter_content(chunk_size=8192):
                tmp.write(chunk)
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
    """
    用 pdfplumber 提取 PDF 正文。
    Returns: {"title": str, "text": str, "pages": int}
    """
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            pages     = len(pdf.pages)
            all_text  = []

            for i, page in enumerate(pdf.pages[:20]):   # 最多取前 20 页
                txt = page.extract_text()
                if txt:
                    all_text.append(txt.strip())

            full_text = "\n".join(all_text)

            # 尝试从首页提取标题（首行往往是标题）
            title = ""
            if all_text:
                first_lines = all_text[0].split("\n")[:4]
                # 标题通常是第一行较短且非纯数字的行
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
        print("  ⚠️  pdfplumber 未安装，尝试回退到 pypdf...")

    # 回退：pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        pages  = len(reader.pages)
        texts  = []
        for page in reader.pages[:20]:
            t = page.extract_text()
            if t:
                texts.append(t)
        full_text = "\n".join(texts)
        return {
            "title": pdf_path.stem,
            "text":  full_text[:MAX_CHARS],
            "pages": pages,
        }
    except Exception as e:
        print(f"  ❌ 文本提取失败: {e}")
        return {"title": pdf_path.stem, "text": "", "pages": 0}


# ── Step 3: LLM 评分（复用 Bouncer prompt）───────────────────────

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
        print("  ❌ 未找到 GEMINI_API_KEY")
        return None

    eval_text = f"PDF 标题: {title}\n总页数: {pages}\n正文片段:\n{text[:3000]}"

    try:
        resp = requests.post(
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
            timeout=30.0,
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
    filepath   = os.path.join(INBOX_DIR, filename)
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

    os.makedirs(INBOX_DIR, exist_ok=True)
    Path(filepath).write_text(content, encoding="utf-8")
    print(f"  📥 已写入 Inbox: {filename}")
    return filepath


# ── Step 5: Telegram 通知 ─────────────────────────────────────────

def notify(source: str, title: str, score: float, reason: str, axiom: str,
           pages: int, written: bool):
    if score >= 9.5:   medal = "💎"
    elif score >= 9.0: medal = "🏆"
    elif score >= 8.5: medal = "🥇"
    elif score >= 8.0: medal = "⭐️"
    else:              medal = "🗑️"

    inbox_line = "📥 已写入 Obsidian Inbox（status: pending）" if written else "❌ 低分，未入库"
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
    """
    完整 PDF 处理流程：获取 → 提取 → 评分 → 写 Inbox → 通知

    Args:
        source:  本地路径或 PDF URL
        silent:  True 时不推送 Telegram

    Returns:
        {"source", "title", "score", "reason", "axiom", "written", "filepath", "pages"}
    """
    print(f"\n📄 [PDF Ingester] 开始处理: {source[:80]}")

    # Step 1: 获取 PDF
    pdf_path = fetch_pdf(source)
    if not pdf_path:
        return {"source": source, "title": "", "score": 0,
                "written": False, "filepath": "", "pages": 0}

    is_temp = source.startswith("http")

    try:
        # Step 2: 提取文本
        print("  📖 提取 PDF 正文（pdfplumber）...")
        extracted = extract_text(pdf_path)
        title     = extracted["title"]
        text      = extracted["text"]
        pages     = extracted["pages"]

        print(f"  📌 标题: {title[:70]}")
        print(f"  📄 共 {pages} 页，提取 {len(text)} 字符")

        if not text:
            print("  ⚠️  正文为空，跳过评分")
            return {"source": source, "title": title, "score": 0,
                    "written": False, "filepath": "", "pages": pages}

        # Step 3: LLM 评分
        print("  🧠 提交给 Gemini 2.0 Flash 评分...")
        result = evaluate(title, text, pages)

        if result is None:
            if not silent:
                send_message(f"📄 PDF Ingester 评分失败\n📚 {title or source[:60]}")
            return {"source": source, "title": title, "score": 0,
                    "written": False, "filepath": "", "pages": pages}

        score  = float(result.get("score", 0))
        reason = result.get("reason", "")
        axiom  = result.get("axiom_extracted", "")

        print(f"  📊 得分: {score:.1f} | 理由: {reason[:60]}")

        # Step 4: 写入 Inbox
        written  = False
        filepath = ""
        if score >= MIN_SCORE_INBOX:
            print("  🏆 高价值内容，写入 Obsidian Inbox...")
            filepath = write_to_inbox(source, title, score, reason, axiom, pages)
            written  = True
        else:
            print(f"  🗑️  低分内容（{score:.1f} < {MIN_SCORE_INBOX}），不入库")

        # Step 5: Telegram
        if not silent:
            notify(source, title, score, reason, axiom, pages, written)

        return {"source": source, "title": title, "score": score,
                "reason": reason, "axiom": axiom,
                "written": written, "filepath": filepath, "pages": pages}

    finally:
        # 清理临时文件
        if is_temp and pdf_path and pdf_path.exists():
            pdf_path.unlink(missing_ok=True)


# ── CLI ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Antigravity PDF Ingester — 评分 PDF 并入库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python skills/global_tools/pdf_ingester/pdf_ingester.py ~/Downloads/paper.pdf
  python skills/global_tools/pdf_ingester/pdf_ingester.py https://arxiv.org/pdf/2303.08774.pdf
  python skills/global_tools/pdf_ingester/pdf_ingester.py /path/to/book.pdf --silent --min-score 7
        """,
    )
    parser.add_argument("source",      help="PDF 文件路径或 URL")
    parser.add_argument("--silent",    action="store_true", help="不推送 Telegram")
    parser.add_argument("--min-score", type=float, default=MIN_SCORE_INBOX,
                        help=f"入库门槛（默认 {MIN_SCORE_INBOX}）")
    args = parser.parse_args()

    MIN_SCORE_INBOX = args.min_score
    result = ingest_pdf(args.source, silent=args.silent)

    print("\n" + "=" * 50)
    print(f"✅ 完成")
    print(f"   标题:  {result.get('title', '')[:50]}")
    print(f"   得分:  {result.get('score', 0):.1f}")
    print(f"   入库:  {'是 → ' + result.get('filepath', '') if result.get('written') else '否'}")
    print("=" * 50)
