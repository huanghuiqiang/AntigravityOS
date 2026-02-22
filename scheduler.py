import schedule
import time
import subprocess
import os
from datetime import datetime

# Change current working directory to /app (container's WORKDIR)
os.chdir('/app')

# Define agent commands and their log files
AGENTS = {
    "daily-briefing": {
        "command": ["python", "agents/daily_briefing/daily_briefing.py"],
        "log_file": "daily_briefing.log",
        "schedule": {"hour": 7, "minute": 50} # 07:50 AM
    },
    "cognitive-bouncer": {
        "command": ["python", "agents/cognitive_bouncer/bouncer.py"],
        "log_file": "cognitive_bouncer.log",
        "schedule": {"hour": 8, "minute": 0} # 08:00 AM
    },
    "knowledge-auditor": {
        "command": ["python", "agents/knowledge_auditor/auditor.py"],
        "log_file": "knowledge_auditor.log",
        "schedule": {"interval": 4, "unit": "hours"} # Every 4 hours
    },
    "inbox-processor": {
        "command": ["python", "agents/inbox_processor/inbox_processor.py"],
        "log_file": "inbox_processor.log",
        "schedule": {"hour": 10, "minute": 30} # 10:30 AM
    },
    # axiom-synthesizer is manual, so no schedule here
}

LOG_DIR = os.path.join("/app", "data", "logs")
# Ensure LOG_DIR exists when scheduler starts
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
    print(f"Scheduler: Created log directory: {LOG_DIR}")
else:
    print(f"Scheduler: Log directory already exists: {LOG_DIR}")
print(f"Scheduler initialized. Log directory: {LOG_DIR}") # Existing print for debugging

def run_agent(agent_name, command, log_file):
    log_path = os.path.join(LOG_DIR, log_file)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Running agent: {agent_name} to {log_path}") # Added log_path for debugging
    try:
        with open(log_path, "a") as f:
            f.write(f"""
--- Agent Run: {timestamp} ---
""")
            try:
                result = subprocess.run(command, capture_output=True, text=True, check=True, env=os.environ.copy()) # Added env for subprocess
                f.write(result.stdout)
                if result.stderr:
                    f.write(f"""--- STDERR ---
{result.stderr}""")
                print(f"[{timestamp}] Agent {agent_name} finished successfully.")
            except subprocess.CalledProcessError as e:
                f.write(f"""--- ERROR ({e.returncode}) ---
STDOUT:
{e.stdout}
STDERR:
{e.stderr}""")
                print(f"[{timestamp}] Agent {agent_name} failed with error: {e.returncode}. Check {log_path}")
            except FileNotFoundError:
                f.write(f"""--- ERROR ---
Command not found: {command[0]}
""")
                print(f"[{timestamp}] Agent {agent_name} failed: Command not found - {command[0]}. Check {log_path}")
            except Exception as e:
                f.write(f"""--- ERROR ---
An unexpected error occurred: {e}
""")
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

    # Schedule the test log writer to run every minute


if __name__ == "__main__":
    print("🚀 Starting Python-based scheduler...")
    # Add project root to PYTHONPATH explicitly for the scheduler process
    # This might be redundant with docker's ENV PYTHONPATH, but good for safety
    if "/app" not in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        os.environ["PYTHONPATH"] = f"/app{os.pathsep}{os.environ.get('PYTHONPATH', '')}"

    schedule_jobs()

    # Run all pending jobs once when starting up (optional, good for testing)
    # print("Running all pending jobs once for startup...")
    # schedule.run_all(delay_seconds=10) # Run immediately with a delay

    while True:
        schedule.run_pending()
        time.sleep(1)
