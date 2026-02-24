from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_rollback_manifest_apply(tmp_path: Path) -> None:
    source = tmp_path / "00_Inbox" / "2026-02-24" / "note.md"
    archived = tmp_path / "00_Inbox" / "Archive" / "dedup" / "2026-02-24" / "note.abc12345.md"
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_text("content", encoding="utf-8")

    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps({"from": str(source), "to": str(archived)}) + "\n", encoding="utf-8")

    cmd = [
        ".venv/bin/python",
        "scripts/rollback_dedup_manifest.py",
        "--manifest",
        str(manifest),
        "--apply",
    ]
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(cmd, cwd=root, check=False, capture_output=True, text=True)

    assert result.returncode == 0
    assert source.exists()
    assert not archived.exists()
