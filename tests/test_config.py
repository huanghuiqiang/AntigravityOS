"""agos.config 单元测试。"""

import os
from pathlib import Path
from agos.config import (
    vault_path, inbox_path, inbox_folder, log_dir,
    openrouter_api_key, telegram_bot_token, telegram_chat_id,
    model_bouncer, model_synthesizer,
    min_score_threshold, project_root,
    commit_digest_repos, feishu_bot_msg_type,
    notify_provider, notify_system_alerts_enabled,
    commit_digest_include_categories, commit_digest_include_risk,
    commit_digest_risk_paths, commit_digest_exclude_types,
)


class TestPaths:
    def test_vault_path_from_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OBSIDIAN_VAULT", str(tmp_path))
        assert vault_path() == tmp_path

    def test_inbox_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OBSIDIAN_VAULT", str(tmp_path))
        assert inbox_path() == tmp_path / "00_Inbox"

    def test_inbox_folder_default(self):
        assert inbox_folder() == "00_Inbox"

    def test_project_root_is_directory(self):
        root = project_root()
        assert root.is_dir()
        assert (root / "agos").is_dir()

    def test_log_dir_created(self, tmp_path, monkeypatch):
        """log_dir() 应该自动创建目录。"""
        d = log_dir()
        assert d.exists()
        assert d.is_dir()


class TestApiKeys:
    def test_openrouter_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-123")
        assert openrouter_api_key() == "sk-test-123"

    def test_openrouter_key_fallback_gemini(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "sk-gemini-456")
        assert openrouter_api_key() == "sk-gemini-456"

    def test_telegram_chat_id(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        assert telegram_chat_id() == "12345"


class TestModels:
    def test_default_bouncer_model(self):
        assert "gemini" in model_bouncer().lower() or "flash" in model_bouncer().lower()

    def test_custom_model_via_env(self, monkeypatch):
        monkeypatch.setenv("MODEL_BOUNCER", "custom/model-v1")
        assert model_bouncer() == "custom/model-v1"


class TestThresholds:
    def test_default_score(self):
        assert min_score_threshold() == 8.0

    def test_custom_score(self, monkeypatch):
        monkeypatch.setenv("MIN_SCORE_THRESHOLD", "7.5")
        assert min_score_threshold() == 7.5


class TestCommitDigest:
    def test_commit_digest_repos_default(self, monkeypatch):
        monkeypatch.delenv("COMMIT_DIGEST_REPOS", raising=False)
        monkeypatch.setenv("GITHUB_DEFAULT_OWNER", "o")
        monkeypatch.setenv("GITHUB_DEFAULT_REPO", "r")
        assert commit_digest_repos() == ["o/r"]

    def test_feishu_bot_msg_type_normalized(self, monkeypatch):
        monkeypatch.setenv("FEISHU_BOT_MSG_TYPE", "TEXT")
        assert feishu_bot_msg_type() == "text"


class TestNotifyConfig:
    def test_notify_provider_default(self, monkeypatch):
        monkeypatch.delenv("NOTIFY_PROVIDER", raising=False)
        assert notify_provider() == "feishu"

    def test_notify_provider_normalized(self, monkeypatch):
        monkeypatch.setenv("NOTIFY_PROVIDER", "TeLeGrAm")
        assert notify_provider() == "telegram"

    def test_notify_switch(self, monkeypatch):
        monkeypatch.setenv("NOTIFY_SYSTEM_ALERTS_ENABLED", "off")
        assert notify_system_alerts_enabled() is False


class TestCommitDigestCategoryConfig:
    def test_commit_digest_include_categories(self, monkeypatch):
        monkeypatch.setenv("COMMIT_DIGEST_INCLUDE_CATEGORIES", "true")
        assert commit_digest_include_categories() is True

    def test_commit_digest_include_risk(self, monkeypatch):
        monkeypatch.setenv("COMMIT_DIGEST_INCLUDE_RISK", "off")
        assert commit_digest_include_risk() is False

    def test_commit_digest_risk_paths(self, monkeypatch):
        monkeypatch.setenv("COMMIT_DIGEST_RISK_PATHS", "a/,b.py")
        assert commit_digest_risk_paths() == ["a/", "b.py"]

    def test_commit_digest_exclude_types(self, monkeypatch):
        monkeypatch.setenv("COMMIT_DIGEST_EXCLUDE_TYPES", "docs,chore")
        assert commit_digest_exclude_types() == {"docs", "chore"}
