import schedule
import time
import subprocess
import os
from pathlib import Path
from datetime import datetime

from agos.config import agent_log_file, project_root

ROOT = project_root()
PYTHON_BIN = os.getenv("PYTHON_BIN", "python")

# Define agent commands and their log files
AGENTS = {
    "daily-briefing": {
        "command": [PYTHON_BIN, "agents/daily_briefing/daily_briefing.py"],
        "log_file": agent_log_file("daily_briefing"),
        "schedule": {"hour": 7, "minute": 50} # 07:50 AM
    },
    "cognitive-bouncer": {
        "command": [PYTHON_BIN, "agents/cognitive_bouncer/bouncer.py"],
        "log_file": agent_log_file("bouncer"),
        "schedule": {"hour": 8, "minute": 0} # 08:00 AM
    },
    "knowledge-auditor": {
        "command": [PYTHON_BIN, "agents/knowledge_auditor/auditor.py"],
        "log_file": agent_log_file("knowledge_auditor"),
        "schedule": {"interval": 4, "unit": "hours"} # Every 4 hours
    },
    "inbox-processor": {
        "command": [PYTHON_BIN, "agents/inbox_processor/inbox_processor.py"],
        "log_file": agent_log_file("inbox_processor"),
        "schedule": {"hour": 10, "minute": 30} # 10:30 AM
    },
    # axiom-synthesizer is manual, so no schedule here
}

LOG_DIR = ROOT / "data" / "logs"
# Ensure LOG_DIR exists when scheduler starts
if not LOG_DIR.exists():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Scheduler: Created log directory: {LOG_DIR}")
else:
    print(f"Scheduler: Log directory already exists: {LOG_DIR}")
print(f"Scheduler initialized. Log directory: {LOG_DIR}") # Existing print for debugging

def run_agent(agent_name, command, log_file):
    log_path = Path(log_file)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    print(f"[{timestamp}] Running agent: {agent_name} to {log_path}")
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"""
--- Agent Run: {timestamp} | agent={agent_name} | run_id={run_id} ---
""")
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=True,
                    env=os.environ.copy(),
                    cwd=ROOT,
                )
                f.write(result.stdout)
                if result.stderr:
                    f.write(f"""--- STDERR ---
{result.stderr}""")
                f.write(f"\n--- END run_id={run_id} | exit_code=0 ---\n")
                print(f"[{timestamp}] Agent {agent_name} finished successfully.")
            except subprocess.CalledProcessError as e:
                f.write(f"""--- ERROR ({e.returncode}) ---
STDOUT:
{e.stdout}
STDERR:
{e.stderr}""")
                f.write(f"\n--- END run_id={run_id} | exit_code={e.returncode} ---\n")
                print(f"[{timestamp}] Agent {agent_name} failed with error: {e.returncode}. Check {log_path}")
            except FileNotFoundError:
                f.write(f"""--- ERROR ---
Command not found: {command[0]}
""")
                f.write(f"\n--- END run_id={run_id} | exit_code=127 ---\n")
                print(f"[{timestamp}] Agent {agent_name} failed: Command not found - {command[0]}. Check {log_path}")
            except Exception as e:
                f.write(f"""--- ERROR ---
An unexpected error occurred: {e}
""")
                f.write(f"\n--- END run_id={run_id} | exit_code=1 ---\n")
                print(f"[{timestamp}] Agent {agent_name} failed: An unexpected error occurred - {e}. Check {log_path}")
    except Exception as file_e:
        print(f"[{timestamp}] CRITICAL ERROR: Could not open/write to log file {log_path}: {file_e}")


def schedule_jobs():
    for agent_name, config in AGENTS.items():
        command = config["command"]
        log_file = config["log_file"]
        schedule_config = config["schedule"]

        if "hour" in schedule_config and "minute" in schedule_config:
            schedule.every().day.at(
                f"{schedule_config['hour']:02d}:{schedule_config['minute']:02d}"
            ).do(run_agent, agent_name, command, log_file)
            print(f"Scheduled {agent_name} daily at {schedule_config['hour']:02d}:{schedule_config['minute']:02d}")
        elif "interval" in schedule_config and "unit" in schedule_config:
            if schedule_config["unit"] == "hours":
                schedule.every(schedule_config["interval"]).hours.do(run_agent, agent_name, command, log_file)
                print(f"Scheduled {agent_name} every {schedule_config['interval']} hours")
            # Add other units if needed (e.g., minutes, days)
        else:
            print(f"Warning: No valid schedule found for {agent_name}")


if __name__ == "__main__":
    print("🚀 Starting Python-based scheduler...")
    # Ensure project root is visible for subprocess imports.
    root_str = str(ROOT)
    py_paths = os.environ.get("PYTHONPATH", "").split(os.pathsep) if os.environ.get("PYTHONPATH") else []
    if root_str not in py_paths:
        os.environ["PYTHONPATH"] = f"{root_str}{os.pathsep}{os.environ.get('PYTHONPATH', '')}".rstrip(os.pathsep)

    schedule_jobs()

    # Run all pending jobs once when starting up (optional, good for testing)
    # print("Running all pending jobs once for startup...")
    # schedule.run_all(delay_seconds=10) # Run immediately with a delay

    while True:
        schedule.run_pending()
        time.sleep(1)
