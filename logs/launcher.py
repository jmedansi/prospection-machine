"""Launch a Python script as a detached process on Windows"""
import subprocess, sys, os

script = os.path.abspath(sys.argv[1])
log = os.path.join(os.path.dirname(script), '..', '..', 'logs', os.path.basename(script).replace('.py', '.log'))

os.makedirs(os.path.dirname(log), exist_ok=True)

proc = subprocess.Popen(
    [sys.executable, script],
    stdout=open(log, 'w'),
    stderr=subprocess.STDOUT,
    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    close_fds=True,
)

print(f"Launched PID={proc.pid} script={script} log={log}")
sys.stdout.flush()
