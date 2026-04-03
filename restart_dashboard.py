#!/usr/bin/env python
"""Force restart Flask dashboard server."""

import subprocess
import time
import sys
import os

# Kill all Python processes listening on port 5001
print("Attempting to restart dashboard...")

try:
    # Get PIDs listening on 5001
    result = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True
    )

    pids_to_kill = set()
    for line in result.stdout.split('\n'):
        if '5001' in line and 'LISTENING' in line:
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids_to_kill.add(int(parts[-1]))

    print(f"Found PIDs: {pids_to_kill}")

    # Kill each PID
    for pid in pids_to_kill:
        try:
            os.system(f"taskkill /PID {pid} /F >nul 2>&1")
            print(f"Killed PID {pid}")
        except:
            pass

    time.sleep(3)

    # Start Flask on port 5001
    os.chdir(r'd:\prospection-machine')
    print("Starting Flask on port 5001...")
    subprocess.Popen([sys.executable, r'dashboard\app.py'])

    time.sleep(3)
    print("Dashboard restarted!")

except Exception as e:
    print(f"Error: {e}")
