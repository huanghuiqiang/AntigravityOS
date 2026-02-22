"""
agos.config
──────────────────
统一配置中心。消灭所有硬编码路径和散落的环境变量读取。

读取优先级：环境变量 > .env 文件 > 默认值
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ── .env 加载（仅执行一次）─────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 按优先级加载：项目根 .env → bouncer .env（兼容旧配置）
load_dotenv(_PROJECT_ROOT / ".env", override=False)
load_dotenv(_PROJECT_ROOT / "agents/cognitive_bouncer/.env", override=False)


# ── 路径 ──────────────────────────────────────────────────────────

def project_root() -> Path:
    """项目根目录（自动检测，不硬编码）。"""
    return _PROJECT_ROOT


def vault_path() -> Path:
    """Obsidian Vault 路径。环境变量 OBSIDIAN_VAULT 可覆盖。"""
    return Path(os.getenv("OBSIDIAN_VAULT", str(_PROJECT_ROOT / "data" / "obsidian_inbox")))


def inbox_path() -> Path:
    """Vault 中的 Inbox 目录。"""
    return vault_path() / inbox_folder()


def inbox_folder() -> str:
    """Inbox 文件夹名（相对于 vault 的子目录名）。"""
    return os.getenv("INBOX_FOLDER", "00_Inbox")


def log_dir() -> Path:
    """日志目录。"""
    d = _PROJECT_ROOT / "data" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_dir() -> Path:
    """运行时状态目录（如去重缓存、游标等）。"""
    d = _PROJECT_ROOT / "data" / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def agent_log_file(agent_name: str) -> Path:
    """统一日志文件路径。"""
    safe = agent_name.strip().replace(" ", "_").replace("-", "_")
    return log_dir() / f"{safe}.log"


def bouncer_log_file() -> Path:
    return log_dir() / "bouncer.log"


def inbox_processor_log_file() -> Path:
    return log_dir() / "inbox_processor.log"


def bouncer_state_file() -> Path:
    """Bouncer 去重 URL 状态文件。"""
    return state_dir() / "processed_urls.json"


def bouncer_feed_config_file() -> Path:
    """Bouncer RSS 配置文件。"""
    return _PROJECT_ROOT / "agents" / "cognitive_bouncer" / "config.json"


# ── API Keys ──────────────────────────────────────────────────────

def openrouter_api_key() -> str:
    """OpenRouter API Key（兼容旧的 GEMINI_API_KEY 命名）。"""
    return os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY", "")


# ── Telegram ──────────────────────────────────────────────────────

def telegram_bot_token() -> str:
    """Telegram Bot Token。优先 .env，其次 OpenClaw 配置。"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        return token
    # 降级：从 OpenClaw 配置读取
    import json
    openclaw_cfg = Path.home() / ".openclaw" / "openclaw.json"
    try:
        with open(openclaw_cfg) as f:
            cfg = json.load(f)
        return cfg.get("channels", {}).get("telegram", {}).get("botToken", "")
    except Exception:
        return ""


def telegram_chat_id() -> str:
    """Telegram Chat ID。"""
    return os.getenv("TELEGRAM_CHAT_ID", "")


# ── 模型 ──────────────────────────────────────────────────────────

def model_bouncer() -> str:
    """Bouncer 使用的模型。"""
    return os.getenv("MODEL_BOUNCER", "google/gemini-2.0-flash-001")


def model_synthesizer() -> str:
    """Axiom Synthesizer 使用的模型。"""
    return os.getenv("MODEL_SYNTHESIZER", "google/gemini-pro-1.5")


# ── 阈值 ──────────────────────────────────────────────────────────

def min_score_threshold() -> float:
    return float(os.getenv("MIN_SCORE_THRESHOLD", "8.0"))


def synth_max_batch() -> int:
    return int(os.getenv("SYNTH_MAX_BATCH", "40"))


def backlog_threshold_days() -> int:
    return int(os.getenv("BACKLOG_THRESHOLD_DAYS", "10"))
