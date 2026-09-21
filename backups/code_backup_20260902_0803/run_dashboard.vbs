Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\prospection-machine"

' Kill any existing Flask processes on port 5001 and 5002
WshShell.Run "cmd /c taskkill /F /FI ""COMMANDLINE eq *dashboard*"" >nul 2>&1", 0, True
WshShell.Run "cmd /c timeout /t 2 >nul", 0, True

' Start Flask dashboard
WshShell.Run "python D:\prospection-machine\dashboard\app.py", 0, False
