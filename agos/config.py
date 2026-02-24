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


def bouncer_dedup_db_file() -> Path:
    """Bouncer 去重索引数据库文件。"""
    return state_dir() / "bouncer_dedup.sqlite3"


def bouncer_lock_file() -> Path:
    """Bouncer 进程锁文件。"""
    return state_dir() / "bouncer.lock"


def bouncer_feed_config_file() -> Path:
    """Bouncer RSS 配置文件。"""
    return _PROJECT_ROOT / "agents" / "cognitive_bouncer" / "config.json"


# ── API Keys ──────────────────────────────────────────────────────

def openrouter_api_key() -> str:
    """OpenRouter API Key（兼容旧的 GEMINI_API_KEY 命名）。"""
    value = os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY")
    return value if isinstance(value, str) else ""


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
        token = cfg.get("channels", {}).get("telegram", {}).get("botToken")
        return token if isinstance(token, str) else ""
    except Exception:
        return ""


def telegram_chat_id() -> str:
    """Telegram Chat ID。"""
    return os.getenv("TELEGRAM_CHAT_ID", "")


# ── 通知治理 ──────────────────────────────────────────────────────

def notify_provider() -> str:
    """系统通知通道：feishu | telegram | none。"""
    provider = os.getenv("NOTIFY_PROVIDER", "feishu").strip().lower()
    if provider in {"feishu", "telegram", "none"}:
        return provider
    return "feishu"


def notify_system_alerts_enabled() -> bool:
    return os.getenv("NOTIFY_SYSTEM_ALERTS_ENABLED", "true").strip().lower() not in {"0", "false", "off"}


def notify_startup_silence_minutes() -> int:
    return max(0, int(os.getenv("NOTIFY_STARTUP_SILENCE_MINUTES", "10")))


def notify_default_cooldown_minutes() -> int:
    return max(0, int(os.getenv("NOTIFY_DEFAULT_COOLDOWN_MINUTES", "60")))


def notify_dedup_db_file() -> Path:
    custom_path = os.getenv("NOTIFY_DEDUP_DB_FILE", "").strip()
    if custom_path:
        return Path(custom_path)
    return state_dir() / "notify.sqlite3"


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


def bouncer_dedup_alert_threshold() -> float:
    return float(os.getenv("BOUNCER_DEDUP_ALERT_THRESHOLD", "30.0"))


def bouncer_alert_suppress_minutes() -> int:
    return int(os.getenv("BOUNCER_ALERT_SUPPRESS_MINUTES", "360"))


def bouncer_dedup_query_drop_prefixes() -> list[str]:
    raw = os.getenv("BOUNCER_DEDUP_QUERY_DROP_PREFIXES", "utm_")
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def bouncer_dedup_query_drop_keys() -> set[str]:
    raw = os.getenv(
        "BOUNCER_DEDUP_QUERY_DROP_KEYS",
        "spm,from,igshid,fbclid,gclid,mc_cid,mc_eid,ref",
    )
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def commit_digest_enabled() -> bool:
    return os.getenv("COMMIT_DIGEST_ENABLED", "true").strip().lower() not in {"0", "false", "off"}


def commit_digest_timezone() -> str:
    return os.getenv("COMMIT_DIGEST_TIMEZONE", "Asia/Shanghai").strip() or "Asia/Shanghai"


def commit_digest_cron() -> str:
    return os.getenv("COMMIT_DIGEST_CRON", "30 21 * * *").strip() or "30 21 * * *"


def commit_digest_repos() -> list[str]:
    raw = os.getenv("COMMIT_DIGEST_REPOS", "").strip()
    if not raw:
        default_owner = os.getenv("GITHUB_DEFAULT_OWNER", "huanghuiqiang").strip() or "huanghuiqiang"
        default_repo = os.getenv("GITHUB_DEFAULT_REPO", "AntigravityOS").strip() or "AntigravityOS"
        return [f"{default_owner}/{default_repo}"]
    return [x.strip() for x in raw.split(",") if x.strip()]


def commit_digest_authors() -> list[str]:
    raw = os.getenv("COMMIT_DIGEST_AUTHORS", "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def commit_digest_max_retries() -> int:
    return int(os.getenv("COMMIT_DIGEST_MAX_RETRIES", "3"))


def commit_digest_retry_backoff_sec() -> int:
    return int(os.getenv("COMMIT_DIGEST_RETRY_BACKOFF_SEC", "2"))


def commit_digest_force_send() -> bool:
    return os.getenv("FORCE_SEND", "false").strip().lower() in {"1", "true", "on"}


def commit_digest_dry_run() -> bool:
    return os.getenv("COMMIT_DIGEST_DRY_RUN", "false").strip().lower() in {"1", "true", "on"}


def commit_digest_alert_on_failure() -> bool:
    return os.getenv("COMMIT_DIGEST_ALERT_ON_FAILURE", "true").strip().lower() not in {"0", "false", "off"}


def commit_digest_state_db_file() -> Path:
    return state_dir() / "commit_digest.sqlite3"


def commit_digest_include_categories() -> bool:
    return os.getenv("COMMIT_DIGEST_INCLUDE_CATEGORIES", "true").strip().lower() not in {"0", "false", "off"}


def commit_digest_include_risk() -> bool:
    return os.getenv("COMMIT_DIGEST_INCLUDE_RISK", "true").strip().lower() not in {"0", "false", "off"}


def commit_digest_risk_paths() -> list[str]:
    raw = os.getenv(
        "COMMIT_DIGEST_RISK_PATHS",
        "scheduler.py,agos/notify.py,docker-compose.yml,apps/tool_gateway/,skills/feishu_bridge/",
    )
    return [item.strip() for item in raw.split(",") if item.strip()]


def commit_digest_exclude_types() -> set[str]:
    raw = os.getenv("COMMIT_DIGEST_EXCLUDE_TYPES", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def commit_digest_max_classify_commits() -> int:
    return max(1, int(os.getenv("COMMIT_DIGEST_MAX_CLASSIFY_COMMITS", "200")))


def commit_digest_max_report_commits() -> int:
    return max(1, int(os.getenv("COMMIT_DIGEST_MAX_REPORT_COMMITS", "200")))


def feishu_bot_webhook() -> str:
    return os.getenv("FEISHU_BOT_WEBHOOK", "").strip()


def feishu_bot_secret() -> str:
    return os.getenv("FEISHU_BOT_SECRET", "").strip()


def feishu_bot_msg_type() -> str:
    msg_type = os.getenv("FEISHU_BOT_MSG_TYPE", "post").strip().lower()
    return msg_type if msg_type in {"post", "text"} else "post"


def synth_max_batch() -> int:
    return int(os.getenv("SYNTH_MAX_BATCH", "40"))


def backlog_threshold_days() -> int:
    return int(os.getenv("BACKLOG_THRESHOLD_DAYS", "10"))
