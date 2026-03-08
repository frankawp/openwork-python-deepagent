#!/usr/bin/env python3
"""
Usage
=====

This script audits Daytona sandboxes against DB threads by aligning:
- Sandbox label: `openwork_thread_id`
- DB key: `threads.id` and `thread_values.daytona.sandbox_id`

Default behavior is read-only. It only deletes when `--delete` is provided.

Examples
--------

From repo root:

1) Read-only audit (14-day orphan threshold):
   server/.venv/bin/python server/scripts/audit_orphan_sandboxes.py --orphan-days 14

2) Write JSON report:
   server/.venv/bin/python server/scripts/audit_orphan_sandboxes.py \
     --orphan-days 14 \
     --json-out .run/orphan_audit.json

3) Delete long-lived orphan sandboxes (max 20):
   server/.venv/bin/python server/scripts/audit_orphan_sandboxes.py \
     --delete \
     --delete-limit 20 \
     --orphan-days 14
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _bootstrap_import_path() -> None:
    server_dir = Path(__file__).resolve().parents[1]
    os.chdir(server_dir)
    server_dir_str = str(server_dir)
    if server_dir_str not in sys.path:
        sys.path.insert(0, server_dir_str)


_bootstrap_import_path()

from daytona import Daytona  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Thread  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Daytona sandboxes against DB threads using label openwork_thread_id. "
            "Default is read-only; pass --delete to remove long-lived orphan sandboxes."
        )
    )
    parser.add_argument(
        "--app-label",
        default="openwork",
        help="Value of Daytona label openwork_app to scope sandboxes (default: openwork).",
    )
    parser.add_argument(
        "--orphan-days",
        type=int,
        default=14,
        help="Only treat orphan sandboxes older than N days as long-lived (default: 14).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Daytona list page size (default: 100).",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete long-lived orphan sandboxes. Without this flag, script is read-only.",
    )
    parser.add_argument(
        "--delete-limit",
        type=int,
        default=50,
        help="Maximum number of orphan sandboxes to delete in one run (default: 50).",
    )
    parser.add_argument(
        "--delete-timeout-sec",
        type=int,
        default=120,
        help="Daytona delete timeout seconds (default: 120).",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write full JSON audit report.",
    )
    return parser.parse_args()


def _parse_utc_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None

    normalized = raw.replace("Z", "+00:00")
    try:
        value = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _get_db_threads() -> list[Thread]:
    db = SessionLocal()
    try:
        return list(db.query(Thread).all())
    finally:
        db.close()


def _get_thread_sandbox_id(thread: Thread) -> str | None:
    values = thread.thread_values if isinstance(thread.thread_values, dict) else {}
    daytona_values = values.get("daytona") if isinstance(values.get("daytona"), dict) else {}
    sandbox_id = daytona_values.get("sandbox_id")
    if isinstance(sandbox_id, str) and sandbox_id:
        return sandbox_id
    return None


def _list_scoped_sandboxes(*, client: Daytona, app_label: str, page_size: int) -> list[Any]:
    sandboxes: list[Any] = []
    page = 1

    while True:
        response = client.list(
            labels={"openwork_app": app_label},
            page=page,
            limit=page_size,
        )
        items = getattr(response, "items", None)
        if isinstance(items, list):
            sandboxes.extend(items)

        total_pages = getattr(response, "total_pages", None)
        if not isinstance(total_pages, int) or total_pages <= 0:
            break
        if page >= total_pages:
            break
        page += 1

    return sandboxes


def _extract_label_thread_id(sandbox: Any) -> str | None:
    labels = getattr(sandbox, "labels", None)
    if not isinstance(labels, dict):
        return None
    thread_id = labels.get("openwork_thread_id")
    if isinstance(thread_id, str) and thread_id:
        return thread_id
    return None


def _extract_sandbox_id(sandbox: Any) -> str:
    value = getattr(sandbox, "id", None)
    return str(value) if value is not None else ""


def _extract_state(sandbox: Any) -> str:
    state = getattr(sandbox, "state", None)
    return str(state)


def _extract_updated_at(sandbox: Any) -> datetime | None:
    return _parse_utc_timestamp(getattr(sandbox, "updated_at", None)) or _parse_utc_timestamp(
        getattr(sandbox, "created_at", None)
    )


def _sandbox_brief(sandbox: Any) -> dict[str, Any]:
    labels = getattr(sandbox, "labels", {})
    labels = labels if isinstance(labels, dict) else {}
    return {
        "sandbox_id": _extract_sandbox_id(sandbox),
        "thread_id_label": labels.get("openwork_thread_id"),
        "state": _extract_state(sandbox),
        "created_at": getattr(sandbox, "created_at", None),
        "updated_at": getattr(sandbox, "updated_at", None),
    }


def _run_audit(args: argparse.Namespace) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=max(args.orphan_days, 0))

    threads = _get_db_threads()
    db_threads_by_id = {thread.id: thread for thread in threads}
    db_thread_ids = set(db_threads_by_id.keys())

    db_sid_by_thread: dict[str, str | None] = {}
    db_sid_to_thread_ids: dict[str, list[str]] = defaultdict(list)
    for thread in threads:
        sid = _get_thread_sandbox_id(thread)
        db_sid_by_thread[thread.id] = sid
        if sid:
            db_sid_to_thread_ids[sid].append(thread.id)

    client = Daytona()
    sandboxes = _list_scoped_sandboxes(
        client=client,
        app_label=args.app_label,
        page_size=max(args.page_size, 1),
    )

    sandbox_by_id: dict[str, Any] = {}
    labeled_sandboxes_by_thread: dict[str, list[Any]] = defaultdict(list)
    unlabeled_or_bad_label: list[Any] = []

    for sandbox in sandboxes:
        sid = _extract_sandbox_id(sandbox)
        if sid:
            sandbox_by_id[sid] = sandbox

        label_thread_id = _extract_label_thread_id(sandbox)
        if label_thread_id:
            labeled_sandboxes_by_thread[label_thread_id].append(sandbox)
        else:
            unlabeled_or_bad_label.append(sandbox)

    orphan_by_label: list[Any] = []
    for thread_id, items in labeled_sandboxes_by_thread.items():
        if thread_id not in db_thread_ids:
            orphan_by_label.extend(items)

    long_lived_orphan: list[Any] = []
    for sandbox in orphan_by_label:
        updated_at = _extract_updated_at(sandbox)
        if updated_at is not None and updated_at < threshold:
            long_lived_orphan.append(sandbox)

    db_thread_missing_sandbox_id = [
        thread_id for thread_id, sandbox_id in db_sid_by_thread.items() if not sandbox_id
    ]

    db_sandbox_id_not_found: list[dict[str, str]] = []
    label_sid_mismatch: list[dict[str, str | None]] = []

    for thread_id, sandbox_id in db_sid_by_thread.items():
        if not sandbox_id:
            continue

        sandbox = sandbox_by_id.get(sandbox_id)
        if sandbox is None:
            db_sandbox_id_not_found.append(
                {
                    "thread_id": thread_id,
                    "sandbox_id": sandbox_id,
                }
            )
            continue

        labeled_thread_id = _extract_label_thread_id(sandbox)
        if labeled_thread_id != thread_id:
            label_sid_mismatch.append(
                {
                    "thread_id": thread_id,
                    "sandbox_id": sandbox_id,
                    "label_thread_id": labeled_thread_id,
                }
            )

    duplicate_sandboxes_per_thread = {
        thread_id: items
        for thread_id, items in labeled_sandboxes_by_thread.items()
        if len(items) > 1
    }

    db_duplicate_sandbox_refs = {
        sandbox_id: thread_ids
        for sandbox_id, thread_ids in db_sid_to_thread_ids.items()
        if len(thread_ids) > 1
    }

    report: dict[str, Any] = {
        "generated_at_utc": now.isoformat(),
        "app_label": args.app_label,
        "orphan_days": args.orphan_days,
        "totals": {
            "db_threads": len(threads),
            "daytona_sandboxes": len(sandboxes),
            "orphan_by_label": len(orphan_by_label),
            "long_lived_orphan": len(long_lived_orphan),
            "unlabeled_or_bad_label": len(unlabeled_or_bad_label),
            "db_thread_missing_sandbox_id": len(db_thread_missing_sandbox_id),
            "db_sandbox_id_not_found": len(db_sandbox_id_not_found),
            "label_sid_mismatch": len(label_sid_mismatch),
            "duplicate_sandboxes_per_thread": len(duplicate_sandboxes_per_thread),
            "db_duplicate_sandbox_refs": len(db_duplicate_sandbox_refs),
        },
        "details": {
            "orphan_by_label": [_sandbox_brief(s) for s in orphan_by_label],
            "long_lived_orphan": [_sandbox_brief(s) for s in long_lived_orphan],
            "unlabeled_or_bad_label": [_sandbox_brief(s) for s in unlabeled_or_bad_label],
            "db_thread_missing_sandbox_id": db_thread_missing_sandbox_id,
            "db_sandbox_id_not_found": db_sandbox_id_not_found,
            "label_sid_mismatch": label_sid_mismatch,
            "duplicate_sandboxes_per_thread": {
                thread_id: [_sandbox_brief(s) for s in items]
                for thread_id, items in duplicate_sandboxes_per_thread.items()
            },
            "db_duplicate_sandbox_refs": db_duplicate_sandbox_refs,
        },
    }

    if args.delete:
        _delete_long_lived_orphans(
            client=client,
            report=report,
            limit=max(args.delete_limit, 0),
            timeout=max(args.delete_timeout_sec, 1),
        )

    return report


def _delete_long_lived_orphans(
    *,
    client: Daytona,
    report: dict[str, Any],
    limit: int,
    timeout: int,
) -> None:
    candidates = report["details"].get("long_lived_orphan", [])
    if not isinstance(candidates, list):
        candidates = []

    deleted: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for item in candidates[:limit]:
        sandbox_id = item.get("sandbox_id") if isinstance(item, dict) else None
        if not isinstance(sandbox_id, str) or not sandbox_id:
            continue

        try:
            sandbox = client.get(sandbox_id)
            client.delete(sandbox, timeout=timeout)
            deleted.append({"sandbox_id": sandbox_id})
        except Exception as exc:  # pragma: no cover - external API
            failed.append(
                {
                    "sandbox_id": sandbox_id,
                    "error": str(exc),
                }
            )

    report["deletion"] = {
        "enabled": True,
        "limit": limit,
        "requested": min(len(candidates), limit),
        "deleted_count": len(deleted),
        "failed_count": len(failed),
        "deleted": deleted,
        "failed": failed,
    }


def _print_report(report: dict[str, Any], deleting: bool) -> None:
    totals = report.get("totals", {})
    if not isinstance(totals, dict):
        totals = {}

    print("=== Daytona Orphan Sandbox Audit ===")
    print(f"generated_at_utc={report.get('generated_at_utc')}")
    print(f"app_label={report.get('app_label')}")
    print(f"orphan_days={report.get('orphan_days')}")
    print()

    for key in [
        "db_threads",
        "daytona_sandboxes",
        "orphan_by_label",
        "long_lived_orphan",
        "unlabeled_or_bad_label",
        "db_thread_missing_sandbox_id",
        "db_sandbox_id_not_found",
        "label_sid_mismatch",
        "duplicate_sandboxes_per_thread",
        "db_duplicate_sandbox_refs",
    ]:
        print(f"{key}={totals.get(key, 0)}")

    if deleting:
        deletion = report.get("deletion", {})
        if not isinstance(deletion, dict):
            deletion = {}
        print()
        print("--- Deletion ---")
        print(f"requested={deletion.get('requested', 0)}")
        print(f"deleted_count={deletion.get('deleted_count', 0)}")
        print(f"failed_count={deletion.get('failed_count', 0)}")

    details = report.get("details", {})
    if not isinstance(details, dict):
        details = {}

    long_lived_orphan = details.get("long_lived_orphan", [])
    if isinstance(long_lived_orphan, list) and long_lived_orphan:
        print()
        print("--- Long-lived orphan sandboxes ---")
        for item in long_lived_orphan[:20]:
            if not isinstance(item, dict):
                continue
            print(
                "sandbox_id={sandbox_id} thread_id_label={thread_id_label} state={state} updated_at={updated_at}".format(
                    sandbox_id=item.get("sandbox_id"),
                    thread_id_label=item.get("thread_id_label"),
                    state=item.get("state"),
                    updated_at=item.get("updated_at"),
                )
            )


def main() -> int:
    args = _parse_args()
    try:
        report = _run_audit(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_report(report, deleting=args.delete)

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print()
        print(f"json_report={args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
