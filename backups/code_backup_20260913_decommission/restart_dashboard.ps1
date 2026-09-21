# Force restart Flask dashboard
Write-Host "Stopping Flask processes on port 5001..."

# Kill all processes listening on port 5001
$netstat = netstat -ano | findstr "5001.*LISTENING"
$pids = @()

foreach ($line in $netstat) {
    $parts = $line -split '\s+'
    if ($parts[-1] -match '^\d+$') {
        $pids += $parts[-1]
    }
}

Write-Host "Found PIDs: $pids"

foreach ($pid in $pids) {
    try {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped process $pid"
    } catch {
        Write-Host "Could not stop process $pid"
    }
}

Start-Sleep -Seconds 2

# Start Flask
Write-Host "Starting Flask on port 5001..."
Set-Location "d:\prospection-machine"
& python dashboard/app.py

Write-Host "Dashboard restarted!"
