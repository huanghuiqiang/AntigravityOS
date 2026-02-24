from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agos.notify import clear_alert_events, list_recent_alert_events


def _cmd_list(limit: int) -> int:
    rows = list_recent_alert_events(limit=limit)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def _cmd_clear(event_key: str | None, yes: bool) -> int:
    if not yes:
        print("Refused to clear. Re-run with --yes to confirm.")
        return 2
    deleted = clear_alert_events(event_key=event_key)
    print(f"deleted={deleted}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect and manage notification dedup state")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="List recent alert dedup records")
    list_parser.add_argument("--limit", type=int, default=20)

    clear_parser = sub.add_parser("clear", help="Clear alert dedup records")
    clear_parser.add_argument("--event-key", default=None)
    clear_parser.add_argument("--yes", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "list":
        return _cmd_list(limit=args.limit)
    if args.command == "clear":
        return _cmd_clear(event_key=args.event_key, yes=args.yes)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
