import psutil
import os

project_profile = r"d:\prospection-machine\data\chrome_profile".lower().replace("\\", "/")

print(f"{'PID':<8} | {'Name':<15} | {'Project?':<8} | {'Headless?':<10} | {'CommandLine'}")
print("-" * 100)

for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        if proc.info['name'] == 'chrome.exe':
            cmdline_list = proc.info.get('cmdline') or []
            cmdline_str = " ".join(cmdline_list).lower().replace("\\", "/")
            
            is_project = project_profile in cmdline_str or "--remote-debugging-port=9222" in cmdline_str
            is_headless = "--headless" in cmdline_str
            
            print(f"{proc.info['pid']:<8} | {proc.info['name']:<15} | {str(is_project):<8} | {str(is_headless):<10} | {cmdline_str[:100]}...")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        continue
