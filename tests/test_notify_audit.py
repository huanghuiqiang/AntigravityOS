from __future__ import annotations

from scripts.notify_audit import main


def test_clear_requires_yes(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("NOTIFY_DEDUP_DB_FILE", str(tmp_path / "notify.sqlite3"))
    code = main(["clear"])
    captured = capsys.readouterr()
    assert code == 2
    assert "Re-run with --yes" in captured.out


def test_list_and_clear(monkeypatch, tmp_path):
    monkeypatch.setenv("NOTIFY_DEDUP_DB_FILE", str(tmp_path / "notify.sqlite3"))
    assert main(["list", "--limit", "1"]) == 0
    assert main(["clear", "--yes"]) == 0
