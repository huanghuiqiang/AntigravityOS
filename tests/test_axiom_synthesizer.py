"""axiom_synthesizer 结构化错误与成功路径测试。"""

import json

import agents.axiom_synthesizer.synthesizer as synth


class _FakeResp:
    def __init__(self, status_code: int, payload: dict, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, *args, **kwargs):
        return self._resp


def test_synthesize_result_missing_api_key(monkeypatch):
    monkeypatch.setattr(synth, "openrouter_api_key", lambda: "")
    result = synth.synthesize_with_llm_result([], set())
    assert result["ok"] is False
    assert result["error_type"] == "missing_api_key"


def test_synthesize_result_http_error(monkeypatch):
    monkeypatch.setattr(synth, "openrouter_api_key", lambda: "sk-test")
    fake_resp = _FakeResp(503, {}, text="upstream unavailable")
    monkeypatch.setattr(synth.httpx, "Client", lambda timeout=60.0: _FakeClient(fake_resp))

    raw = [{"axiom": "x", "title": "t", "path": "/tmp/a.md"}]
    result = synth.synthesize_with_llm_result(raw, set())
    assert result["ok"] is False
    assert result["error_type"] == "llm_http_error"
    assert result["processed_paths"] == ["/tmp/a.md"]


def test_synthesize_result_success_with_dict_payload(monkeypatch):
    monkeypatch.setattr(synth, "openrouter_api_key", lambda: "sk-test")
    content = json.dumps(
        {
            "items": [
                {
                    "name": "Feedback Loop",
                    "meaning": "closed loop beats open loop",
                    "sources": ["src-1"],
                    "is_new": True,
                }
            ]
        },
        ensure_ascii=False,
    )
    fake_resp = _FakeResp(
        200,
        {"choices": [{"message": {"content": content}}]},
    )
    monkeypatch.setattr(synth.httpx, "Client", lambda timeout=60.0: _FakeClient(fake_resp))

    raw = [{"axiom": "x", "title": "t", "path": "/tmp/a.md"}]
    result = synth.synthesize_with_llm_result(raw, set())
    assert result["ok"] is True
    assert len(result["synthesized"]) == 1
    assert result["synthesized"][0]["name"] == "Feedback Loop"
