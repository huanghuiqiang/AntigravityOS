"""agos.notify 单元测试。"""

from unittest.mock import patch, MagicMock
from agos.notify import send_message, send_bouncer_report


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
        assert "💎" in call_text  # 9.5 分应该是 💎
