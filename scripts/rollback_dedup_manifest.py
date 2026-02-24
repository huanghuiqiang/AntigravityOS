from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rollback dedup archive moves using manifest.")
    parser.add_argument("--manifest", type=Path, required=True, help="Manifest jsonl path.")
    parser.add_argument("--apply", action="store_true", help="Apply rollback. Default dry-run.")
    return parser.parse_args()


def _load_manifest(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if not isinstance(data, dict):
                continue
            src = str(data.get("from", "")).strip()
            dst = str(data.get("to", "")).strip()
            if src and dst:
                rows.append({"from": src, "to": dst})
    return rows


def main() -> int:
    args = parse_args()
    manifest = args.manifest.expanduser().resolve()
    if not manifest.exists():
        print(f"[error] manifest not found: {manifest}")
        return 1

    rows = _load_manifest(manifest)
    if not rows:
        print("[error] empty manifest")
        return 1

    moved = 0
    for row in rows:
        original = Path(row["from"])
        archived = Path(row["to"])
        if not archived.exists():
            print(f"[skip] archived file missing: {archived}")
            continue

        if args.apply:
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(archived), str(original))
            moved += 1
            print(f"[restored] {archived} -> {original}")
        else:
            print(f"[dry-run] restore {archived} -> {original}")

    mode = "apply" if args.apply else "dry-run"
    print(f"[done] mode={mode} rows={len(rows)} moved={moved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
