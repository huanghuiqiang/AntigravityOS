"""cognitive_bouncer 关键流程测试。"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_bouncer_module():
    root = Path(__file__).resolve().parents[1]
    mod_path = root / "agents" / "cognitive_bouncer" / "bouncer.py"
    spec = spec_from_file_location("cognitive_bouncer_bouncer", mod_path)
    assert spec and spec.loader
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_processed_state_roundtrip(tmp_path):
    bouncer = _load_bouncer_module()
    bouncer.DB_FILE = tmp_path / "processed_urls.json"

    src = {"https://a.com", "https://b.com"}
    bouncer.save_processed(src)
    loaded = bouncer.load_processed()

    assert loaded == src
    assert bouncer.DB_FILE.exists()


def test_export_to_inbox_writes_note(tmp_vault):
    bouncer = _load_bouncer_module()

    bouncer.export_to_inbox(
        title="A/B Test: Practical Systems",
        url="https://example.com/article",
        score=9.1,
        reason="contains practical systems insight",
        axiom="Feedback loops beat one-shot optimization.",
    )

    note_path = tmp_vault / "00_Inbox" / "Bouncer - AB Test Practical Systems.md"
    assert note_path.exists(), "expected bouncer note written to Inbox"
    content = note_path.read_text(encoding="utf-8")
    assert "status: pending" in content
    assert "Feedback loops beat one-shot optimization." in content
