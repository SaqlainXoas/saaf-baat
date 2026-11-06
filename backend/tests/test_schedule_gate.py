import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from schedule_gate import PKT, decision  # noqa: E402


def test_gate_outputs_manual_mode_for_workflow_dispatch(monkeypatch, tmp_path):
    from schedule_gate import main

    output = tmp_path / "output"
    summary = tmp_path / "summary"
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    main()
    assert output.read_text() == "run=true\nmode=manual\n"
    assert "explicit_manual_run" in summary.read_text()


@pytest.mark.parametrize("hour,minute,run,reason", [
    (4, 59, False, "outside_generation_window"),
    (5, 0, True, "morning_generation_window"),
    (11, 14, True, "morning_generation_window"),
    (11, 15, False, "outside_generation_window"),
    (12, 0, True, "publication_deadline_audit"),
    (12, 59, True, "publication_deadline_audit"),
    (13, 0, False, "outside_generation_window"),
    (23, 59, False, "outside_generation_window"),
])
def test_actual_pkt_window(hour, minute, run, reason):
    now = datetime(2026, 11, 6, hour, minute, tzinfo=PKT)
    assert decision("schedule", now.astimezone(timezone.utc)) == (run, "backup", reason)


def test_manual_dispatch_remains_available_after_noon():
    assert decision("workflow_dispatch", datetime(2026, 11, 6, 14, tzinfo=PKT)) == (
        True, "manual", "explicit_manual_run",
    )


def test_delayed_overnight_ticks_supply_morning_opportunities():
    # Replay a six-hour dispatch delay across a day. Overnight ticks are useful
    # wakeups next morning; actual time, rather than original cron hour, wins.
    ticks = [datetime(2026, 11, 5, 20, 17, tzinfo=timezone.utc) + timedelta(hours=i)
             for i in range(24)]
    allowed = [tick + timedelta(hours=6) for tick in ticks
               if decision("schedule", tick + timedelta(hours=6))[2] == "morning_generation_window"]
    assert len(allowed) >= 5
    assert all(5 <= tick.astimezone(PKT).hour < 12 for tick in allowed)


def test_workflow_routes_every_schedule_to_recovery_and_gates_installs():
    workflow = yaml.safe_load((Path(__file__).resolve().parents[2] /
                               ".github/workflows/daily_pipeline.yml").read_text())
    # PyYAML's YAML 1.1 loader reads the key `on` as True.
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["schedule"] == [{"cron": "17 * * * *"}]
    steps = workflow["jobs"]["publish"]["steps"]
    gate = next(i for i, step in enumerate(steps) if step.get("id") == "gate")
    for i, step in enumerate(steps):
        if "setup-python" in step.get("uses", "") or step.get("name") in {
            "Install pipeline", "Generate, recover and publish the edition",
        }:
            assert i > gate
            assert step["if"] == "steps.gate.outputs.run == 'true'"
