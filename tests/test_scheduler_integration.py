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
