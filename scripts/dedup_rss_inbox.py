from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agos.config import inbox_path
from agos.frontmatter import parse_frontmatter

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WS_RE = re.compile(r"\s+")
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {"spm", "from", "igshid", "fbclid", "gclid", "mc_cid", "mc_eid", "ref"}


@dataclass(frozen=True)
class NoteMeta:
    path: Path
    group_date: date
    created: date
    title: str
    normalized_title: str
    source: str
    normalized_source: str
    source_host: str


@dataclass(frozen=True)
class DuplicateDecision:
    keep: NoteMeta
    duplicate: NoteMeta
    key: str
    reason: str


def normalize_title(title: str) -> str:
    lowered = title.strip().lower()
    return _WS_RE.sub(" ", lowered)


def normalize_url(url: str) -> tuple[str, str]:
    raw = (url or "").strip()
    if not raw:
        return "", ""

    parts = urlsplit(raw)
    scheme = (parts.scheme or "https").lower()
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")

    query_items: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lower_key = key.lower()
        if lower_key.startswith(_TRACKING_QUERY_PREFIXES):
            continue
        if lower_key in _TRACKING_QUERY_KEYS:
            continue
        query_items.append((key, value))
    query = urlencode(sorted(query_items), doseq=True)

    normalized = urlunsplit((scheme, host, path, query, ""))
    return normalized, host


def parse_date_str(raw: str) -> date | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def date_from_path(path: Path, inbox_root: Path) -> date | None:
    try:
        rel = path.relative_to(inbox_root)
    except ValueError:
        return None

    for part in rel.parts:
        if _DATE_RE.match(part):
            return datetime.strptime(part, "%Y-%m-%d").date()
    return None


def in_date_scope(group_date: date, start: date | None, end: date | None) -> bool:
    if start and group_date < start:
        return False
    if end and group_date > end:
        return False
    return True


def _has_bouncer_tag(frontmatter: dict) -> bool:
    tags = frontmatter.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list):
        return False
    normalized = {str(item).strip() for item in tags}
    return "BouncerDump" in normalized


def read_note_meta(path: Path, inbox_root: Path) -> NoteMeta | None:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None

    frontmatter, _ = parse_frontmatter(content)
    if not _has_bouncer_tag(frontmatter):
        return None

    title_raw = str(frontmatter.get("title", "")).strip()
    if not title_raw:
        title_raw = path.stem

    source_raw = str(frontmatter.get("source", "")).strip()
    normalized_source, source_host = normalize_url(source_raw)
    normalized_title = normalize_title(title_raw)

    path_date = date_from_path(path, inbox_root)
    created = parse_date_str(str(frontmatter.get("created", "")))
    group_date = path_date or created
    if group_date is None:
        return None

    return NoteMeta(
        path=path,
        group_date=group_date,
        created=created or group_date,
        title=title_raw,
        normalized_title=normalized_title,
        source=source_raw,
        normalized_source=normalized_source,
        source_host=source_host,
    )


def build_dedup_key(note: NoteMeta) -> tuple[str, str]:
    if note.normalized_source:
        return f"src:{note.normalized_source}", "same_source"

    fallback = f"fallback:{note.source_host}|{note.normalized_title}"
    return fallback, "same_title_same_source"


def should_keep(candidate: NoteMeta, current_keep: NoteMeta) -> bool:
    if candidate.created != current_keep.created:
        return candidate.created < current_keep.created
    return str(candidate.path) < str(current_keep.path)


def find_duplicates(notes: list[NoteMeta]) -> list[DuplicateDecision]:
    keepers: dict[str, NoteMeta] = {}
    duplicates: list[DuplicateDecision] = []

    ordered = sorted(notes, key=lambda x: (x.created, str(x.path)))
    for note in ordered:
        key, reason = build_dedup_key(note)
        if key not in keepers:
            keepers[key] = note
            continue

        keep_note = keepers[key]
        if should_keep(note, keep_note):
            duplicates.append(DuplicateDecision(keep=note, duplicate=keep_note, key=key, reason=reason))
            keepers[key] = note
            continue

        duplicates.append(DuplicateDecision(keep=keep_note, duplicate=note, key=key, reason=reason))

    return duplicates


def archive_destination(inbox_root: Path, path: Path, archive_root: Path) -> Path:
    rel = path.relative_to(inbox_root)
    digest = hashlib.sha1(str(rel).encode("utf-8")).hexdigest()[:8]
    return archive_root / rel.parent / f"{rel.stem}.{digest}{rel.suffix}"


def move_duplicate(inbox_root: Path, duplicate: NoteMeta, archive_root: Path) -> Path:
    target = archive_destination(inbox_root, duplicate.path, archive_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(duplicate.path), str(target))
    return target


def _default_manifest_path(inbox_root: Path) -> Path:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return inbox_root / "Archive" / "dedup" / f"manifest-{ts}.jsonl"


def _write_manifest(manifest_path: Path, entries: list[dict[str, str]]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as handle:
        for item in entries:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deduplicate RSS bouncer notes in inbox.")
    parser.add_argument("--inbox", type=Path, default=inbox_path(), help="Inbox root directory.")
    parser.add_argument("--start", type=str, default="", help="Start date, YYYY-MM-DD (inclusive).")
    parser.add_argument("--end", type=str, default="", help="End date, YYYY-MM-DD (inclusive).")
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=None,
        help="Archive root for duplicates. Default: <inbox>/Archive/dedup",
    )
    parser.add_argument("--manifest-out", type=Path, default=None, help="Manifest output path for apply mode.")
    parser.add_argument("--apply", action="store_true", help="Apply archive move. Default dry-run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inbox_root = args.inbox.expanduser().resolve()
    if not inbox_root.exists():
        print(f"[error] inbox not found: {inbox_root}")
        return 1

    start = parse_date_str(args.start)
    end = parse_date_str(args.end)
    if args.start and start is None:
        print(f"[error] invalid --start: {args.start}")
        return 1
    if args.end and end is None:
        print(f"[error] invalid --end: {args.end}")
        return 1
    if start and end and start > end:
        print("[error] --start is after --end")
        return 1

    archive_root = args.archive_dir or (inbox_root / "Archive" / "dedup")
    archive_root = archive_root.expanduser().resolve()

    note_files = sorted(inbox_root.rglob("*.md"))
    notes: list[NoteMeta] = []
    for path in note_files:
        if archive_root in path.parents:
            continue
        note = read_note_meta(path, inbox_root)
        if note is None:
            continue
        if not in_date_scope(note.group_date, start, end):
            continue
        notes.append(note)

    duplicates = find_duplicates(notes)

    moved = 0
    manifest_entries: list[dict[str, str]] = []
    if args.apply:
        for decision in duplicates:
            moved_target = move_duplicate(inbox_root, decision.duplicate, archive_root)
            moved += 1
            manifest_entries.append(
                {
                    "from": str(decision.duplicate.path),
                    "to": str(moved_target),
                    "keep": str(decision.keep.path),
                    "key": decision.key,
                    "reason": decision.reason,
                }
            )
            print(
                f"[moved] {decision.duplicate.path} -> {moved_target} "
                f"(key={decision.key}, reason={decision.reason})"
            )
        if manifest_entries:
            manifest_path = args.manifest_out.expanduser().resolve() if args.manifest_out else _default_manifest_path(inbox_root)
            _write_manifest(manifest_path, manifest_entries)
            print(f"[manifest] wrote {len(manifest_entries)} rows to {manifest_path}")
    else:
        for decision in duplicates:
            print(
                f"[dry-run] duplicate={decision.duplicate.path} keep={decision.keep.path} "
                f"(key={decision.key}, reason={decision.reason})"
            )

    total = len(notes)
    dup_count = len(duplicates)
    ratio = (dup_count / total * 100.0) if total else 0.0
    mode = "apply" if args.apply else "dry-run"
    print("-" * 80)
    print(
        f"mode={mode} inbox={inbox_root} start={start or '-'} end={end or '-'} "
        f"total={total} duplicates={dup_count} dedup_rate={ratio:.2f}% moved={moved}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
