"""stats 结构化告警输出测试。"""

import json

from scripts import stats


def test_warn_outputs_json(capsys):
    stats._warn("stats/test", "something happened")
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["level"] == "WARN"
    assert payload["scope"] == "stats/test"
    assert payload["detail"] == "something happened"
    assert "ts" in payload


def test_warn_outputs_error_fields(capsys):
    stats._warn("stats/test", "failed", ValueError("bad value"))
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["error"] == "bad value"
    assert payload["error_type"] == "ValueError"
