"""agos.notify 单元测试。"""

from unittest.mock import MagicMock, patch

from agos.notify import (
    clear_alert_events,
    list_recent_alert_events,
    send_bouncer_report,
    send_message,
    send_system_alert,
)


class TestSendMessage:
    def test_missing_token_returns_false(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
        assert send_message("test") is False

    def test_missing_chat_id_returns_false(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
        assert send_message("test") is False

    @patch("agos.notify.requests.post")
    def test_successful_send(self, mock_post, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        result = send_message("Hello!")
        assert result is True
        mock_post.assert_called_once()

    @patch("agos.notify.requests.post")
    def test_api_error_returns_false(self, mock_post, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        mock_post.return_value = mock_resp

        result = send_message("Hello!")
        assert result is False


class TestSendBouncerReport:
    @patch("agos.notify.send_message")
    def test_empty_articles(self, mock_send):
        mock_send.return_value = True
        result = send_bouncer_report([], 10)
        assert result is True
        call_text = mock_send.call_args[0][0]
        assert "10" in call_text
        assert "全部过滤" in call_text

    @patch("agos.notify.send_message")
    def test_with_golden_articles(self, mock_send):
        mock_send.return_value = True
        articles = [
            {"title": "Great Article", "url": "https://x.com/a", "score": 9.5, "axiom": "Test axiom"},
        ]
        result = send_bouncer_report(articles, 5)
        assert result is True
        call_text = mock_send.call_args[0][0]
        assert "Great Article" in call_text
        assert "💎" in call_text


class TestSystemAlert:
    def test_provider_none_returns_false(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NOTIFY_PROVIDER", "none")
        monkeypatch.setenv("NOTIFY_STARTUP_SILENCE_MINUTES", "0")
        monkeypatch.setenv("NOTIFY_DEDUP_DB_FILE", str(tmp_path / "notify.sqlite3"))
        clear_alert_events()
        ok = send_system_alert(
            event_key="scheduler:test-a",
            level="CRITICAL",
            text="hello",
            meta={"state": "fail", "trace_id": "t1", "component": "scheduler"},
        )
        assert ok is False

    @patch("agos.notify.send_feishu_webhook")
    def test_dedup_suppresses_second_fail(self, mock_send, monkeypatch, tmp_path):
        monkeypatch.setenv("NOTIFY_PROVIDER", "feishu")
        monkeypatch.setenv("NOTIFY_STARTUP_SILENCE_MINUTES", "0")
        monkeypatch.setenv("NOTIFY_DEFAULT_COOLDOWN_MINUTES", "60")
        monkeypatch.setenv("NOTIFY_DEDUP_DB_FILE", str(tmp_path / "notify.sqlite3"))
        monkeypatch.setenv("FEISHU_BOT_WEBHOOK", "https://open.feishu.cn/open-apis/bot/v2/hook/test")
        mock_send.return_value = {"code": 0}
        clear_alert_events()

        first = send_system_alert(
            event_key="scheduler:test-b",
            level="CRITICAL",
            text="failed",
            meta={"state": "fail", "trace_id": "t1", "component": "scheduler"},
        )
        second = send_system_alert(
            event_key="scheduler:test-b",
            level="CRITICAL",
            text="failed again",
            meta={"state": "fail", "trace_id": "t2", "component": "scheduler"},
        )
        assert first is True
        assert second is False
        assert mock_send.call_count == 1

    @patch("agos.notify.send_feishu_webhook")
    def test_recovery_not_suppressed(self, mock_send, monkeypatch, tmp_path):
        monkeypatch.setenv("NOTIFY_PROVIDER", "feishu")
        monkeypatch.setenv("NOTIFY_STARTUP_SILENCE_MINUTES", "0")
        monkeypatch.setenv("NOTIFY_DEFAULT_COOLDOWN_MINUTES", "60")
        monkeypatch.setenv("NOTIFY_DEDUP_DB_FILE", str(tmp_path / "notify.sqlite3"))
        monkeypatch.setenv("FEISHU_BOT_WEBHOOK", "https://open.feishu.cn/open-apis/bot/v2/hook/test")
        mock_send.return_value = {"code": 0}
        clear_alert_events()

        send_system_alert(
            event_key="scheduler:test-c",
            level="CRITICAL",
            text="failed",
            meta={"state": "fail", "trace_id": "t1", "component": "scheduler"},
        )
        recovered = send_system_alert(
            event_key="scheduler:test-c",
            level="INFO",
            text="recovered",
            meta={"state": "recover", "trace_id": "t2", "component": "scheduler"},
        )
        assert recovered is True
        assert mock_send.call_count == 2

    @patch("agos.notify.send_feishu_webhook")
    def test_startup_silence_suppresses(self, mock_send, monkeypatch, tmp_path):
        monkeypatch.setenv("NOTIFY_PROVIDER", "feishu")
        monkeypatch.setenv("NOTIFY_STARTUP_SILENCE_MINUTES", "30")
        monkeypatch.setenv("NOTIFY_DEDUP_DB_FILE", str(tmp_path / "notify.sqlite3"))
        monkeypatch.setenv("FEISHU_BOT_WEBHOOK", "https://open.feishu.cn/open-apis/bot/v2/hook/test")
        clear_alert_events()

        ok = send_system_alert(
            event_key="scheduler:test-d",
            level="CRITICAL",
            text="failed",
            meta={"state": "fail", "trace_id": "t1", "component": "scheduler"},
        )
        assert ok is False
        mock_send.assert_not_called()

    @patch("agos.notify.send_feishu_webhook")
    def test_list_recent_alert_events(self, mock_send, monkeypatch, tmp_path):
        monkeypatch.setenv("NOTIFY_PROVIDER", "feishu")
        monkeypatch.setenv("NOTIFY_STARTUP_SILENCE_MINUTES", "0")
        monkeypatch.setenv("NOTIFY_DEDUP_DB_FILE", str(tmp_path / "notify.sqlite3"))
        monkeypatch.setenv("FEISHU_BOT_WEBHOOK", "https://open.feishu.cn/open-apis/bot/v2/hook/test")
        mock_send.return_value = {"code": 0}
        clear_alert_events()
        send_system_alert(
            event_key="scheduler:test-e",
            level="CRITICAL",
            text="failed",
            meta={"state": "fail", "trace_id": "t1", "component": "scheduler"},
        )
        rows = list_recent_alert_events(limit=5)
        assert rows
        assert rows[0]["event_key"] == "scheduler:test-e"
