"""Gate hourly wakeups by actual Pakistan time, before installing pipeline deps."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PKT = ZoneInfo("Asia/Karachi")


def decision(event: str, now: datetime) -> tuple[bool, str, str]:
    if event == "workflow_dispatch":
        return True, "manual", "explicit_manual_run"
    if event != "schedule":
        raise ValueError(f"Unsupported pipeline event: {event}")
    local = now.astimezone(PKT)
    minute = local.hour * 60 + local.minute
    # Leave 45 minutes before noon for generation and publication. Each tick
    # resumes valid same-day drafts, or generates afresh if there are none.
    if 5 * 60 <= minute < 11 * 60 + 15:
        return True, "backup", "morning_generation_window"
    # Keep a missed edition visible as a real failure, rather than making all
    # late ticks green. daily_run skips a published edition or records failure.
    if 12 * 60 <= minute < 13 * 60:
        return True, "backup", "publication_deadline_audit"
    return False, "backup", "outside_generation_window"


def main() -> None:
    now = datetime.now(PKT)
    run, mode, reason = decision(os.environ["GITHUB_EVENT_NAME"], now)
    message = f"{now.isoformat()}: run={run}, mode={mode}, reason={reason}"
    print(message)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"run={str(run).lower()}\nmode={mode}\n")
    if summary := os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a") as output:
            output.write(f"Pipeline schedule gate: {message}\n")


if __name__ == "__main__":
    main()
