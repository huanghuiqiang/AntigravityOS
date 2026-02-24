"""scheduler 触发与日志写入测试。"""

import sys
import types

# scheduler.py 在模块加载时 import schedule；测试环境可能未安装该依赖。
if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")

import scheduler


def test_run_agent_writes_log_with_exit_code(tmp_path, monkeypatch):
    log_file = tmp_path / "bouncer.log"

    monkeypatch.setattr(scheduler, "ROOT", tmp_path)
    monkeypatch.setattr(scheduler, "LOG_DIR", tmp_path)

    scheduler.run_agent(
        agent_name="bouncer",
        command=[sys.executable, "-c", "print('hello from test')"],
        log_file=str(log_file),
    )

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "Agent Run" in content
    assert "hello from test" in content
    assert "exit_code=0" in content


class _FakeJob:
    def __init__(self, registry, day: str | None = None):
        self._registry = registry
        self._day = day

    def __getattr__(self, name: str):
        return _FakeJob(self._registry, day=name)

    def at(self, time_str: str):
        self._time = time_str
        return self

    @property
    def day(self):
        return self

    @property
    def hours(self):
        return self

    def do(self, fn, agent_name, command, log_file):
        self._registry.append(
            {"day": self._day, "agent": agent_name, "command": command, "log_file": log_file}
        )
        return self


class _FakeSchedule:
    def __init__(self):
        self.calls = []

    def every(self, *args, **kwargs):
        return _FakeJob(self.calls)


def test_schedule_jobs_supports_weekly(monkeypatch):
    fake_schedule = _FakeSchedule()
    monkeypatch.setattr(scheduler, "schedule", fake_schedule)
    monkeypatch.setattr(scheduler, "commit_digest_enabled", lambda: False)
    monkeypatch.setattr(
        scheduler,
        "AGENTS",
        {
            "weekly-agent": {
                "command": [sys.executable, "-c", "print('ok')"],
                "log_file": "weekly.log",
                "schedule": {"day_of_week": "monday", "hour": 9, "minute": 0},
            }
        },
    )

    scheduler.schedule_jobs()
    assert len(fake_schedule.calls) == 1
    assert fake_schedule.calls[0]["agent"] == "weekly-agent"
    assert fake_schedule.calls[0]["day"] == "monday"


def test_schedule_jobs_skips_invalid_weekday(monkeypatch):
    fake_schedule = _FakeSchedule()
    monkeypatch.setattr(scheduler, "schedule", fake_schedule)
    monkeypatch.setattr(scheduler, "commit_digest_enabled", lambda: False)
    monkeypatch.setattr(
        scheduler,
        "AGENTS",
        {
            "bad-weekly-agent": {
                "command": [sys.executable, "-c", "print('ok')"],
                "log_file": "weekly.log",
                "schedule": {"day_of_week": "funday", "hour": 9, "minute": 0},
            }
        },
    )

    scheduler.schedule_jobs()
    assert fake_schedule.calls == []


def test_run_agent_sends_failure_alert_with_trace_id(tmp_path, monkeypatch):
    log_file = tmp_path / "failed.log"
    alerts = []

    monkeypatch.setattr(scheduler, "ROOT", tmp_path)
    monkeypatch.setattr(scheduler, "LOG_DIR", tmp_path)
    monkeypatch.setattr(
        scheduler,
        "send_system_alert",
        lambda **kwargs: alerts.append(kwargs) or True,
    )

    scheduler.run_agent(
        agent_name="broken-agent",
        command=[sys.executable, "-c", "import sys;print('trace_id=abc123xyz');sys.exit(2)"],
        log_file=str(log_file),
    )

    assert log_file.exists()
    assert alerts, "expected failure alert to be sent"
    assert alerts[0]["event_key"] == "scheduler:broken-agent"
    assert alerts[0]["meta"]["trace_id"] == "abc123xyz"


def test_parse_daily_cron() -> None:
    minute, hour = scheduler._parse_daily_cron("30 21 * * *")
    assert minute == 30
    assert hour == 21


def test_schedule_jobs_adds_commit_digest_from_env(monkeypatch):
    fake_schedule = _FakeSchedule()
    monkeypatch.setattr(scheduler, "schedule", fake_schedule)
    monkeypatch.setattr(scheduler, "AGENTS", {})
    monkeypatch.setattr(scheduler, "commit_digest_enabled", lambda: True)
    monkeypatch.setattr(scheduler, "commit_digest_cron", lambda: "30 21 * * *")

    scheduler.schedule_jobs()
    assert len(fake_schedule.calls) == 1
    assert fake_schedule.calls[0]["agent"] == "daily-commit-bot-push"
