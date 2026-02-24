from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "dedup_rss_inbox.py"
SPEC = importlib.util.spec_from_file_location("dedup_rss_inbox", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("failed to load dedup_rss_inbox module")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write_note(path: Path, title: str, source: str, created: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "---\n"
            f"title: \"{title}\"\n"
            f"source: \"{source}\"\n"
            f"created: \"{created}\"\n"
            "tags:\n"
            "  - BouncerDump\n"
            "---\n\n"
            f"# {title}\n"
        ),
        encoding="utf-8",
    )


def _write_non_bouncer(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "---\n"
            "title: \"Manual Note\"\n"
            "tags:\n"
            "  - Manual\n"
            "---\n\n"
            "# Manual Note\n"
        ),
        encoding="utf-8",
    )


def test_find_duplicates_same_source_url(tmp_path: Path) -> None:
    inbox = tmp_path / "00_Inbox"
    keep_file = inbox / "2026-02-21" / "Bouncer - one.md"
    dup_file = inbox / "2026-02-22" / "Bouncer - two.md"

    _write_note(
        keep_file,
        title="Anthropic Distillation",
        source="https://example.com/post?id=1&utm_source=foo",
        created="2026-02-21",
    )
    _write_note(
        dup_file,
        title="Anthropic Distillation",
        source="https://example.com/post?id=1&utm_medium=bar",
        created="2026-02-22",
    )

    note_a = MODULE.read_note_meta(keep_file, inbox)
    note_b = MODULE.read_note_meta(dup_file, inbox)

    assert note_a is not None
    assert note_b is not None

    duplicates = MODULE.find_duplicates([note_b, note_a])
    assert len(duplicates) == 1
    decision = duplicates[0]
    assert decision.keep.path == keep_file
    assert decision.duplicate.path == dup_file
    assert decision.reason == "same_source"


def test_non_bouncer_note_is_ignored(tmp_path: Path) -> None:
    inbox = tmp_path / "00_Inbox"
    note = inbox / "2026-02-22" / "manual.md"
    _write_non_bouncer(note)
    assert MODULE.read_note_meta(note, inbox) is None


def test_move_duplicate_to_archive(tmp_path: Path) -> None:
    inbox = tmp_path / "00_Inbox"
    keep_file = inbox / "2026-02-23" / "Bouncer - keep.md"
    dup_file = inbox / "2026-02-24" / "Bouncer - dup.md"

    _write_note(
        keep_file,
        title="Weekly AI Infra",
        source="https://another.example.com/news",
        created="2026-02-23",
    )
    _write_note(
        dup_file,
        title="Weekly AI Infra",
        source="https://another.example.com/news",
        created="2026-02-24",
    )

    note_keep = MODULE.read_note_meta(keep_file, inbox)
    note_dup = MODULE.read_note_meta(dup_file, inbox)
    assert note_keep is not None
    assert note_dup is not None

    archive_root = inbox / "Archive" / "dedup"
    moved_path = MODULE.move_duplicate(inbox, note_dup, archive_root)

    assert not dup_file.exists()
    assert moved_path.exists()
    assert moved_path.parent == archive_root / "2026-02-24"
