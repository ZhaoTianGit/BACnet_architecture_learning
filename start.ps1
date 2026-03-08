# start.ps1 - Run EVERY SESSION to launch the BACnet Dashboard

Write-Host "========================================"
Write-Host " BACnet Dashboard - Starting Up"
Write-Host "========================================"

# Fix PATH for this session
$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","User")

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$dashboardDir = Join-Path $projectDir "bacnet-dashboard"

# Remind user to check the port
Write-Host ""
Write-Host "REMINDER: Check Yabe for the current DUT port"
Write-Host "Then update cfg.dut.port in api_server.py"
Write-Host ""
Read-Host "Press ENTER when port is updated"

# Launch Python backend in new window
Write-Host ""
Write-Host "[1/2] Starting Python backend (uvicorn)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$projectDir'; `$env:PATH = [System.Environment]::GetEnvironmentVariable('PATH','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('PATH','User'); uvicorn api_server:app --reload"

Write-Host "      Waiting for backend to start..."
Start-Sleep -Seconds 4

# Check backend health
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 3
    Write-Host "      Backend OK - DUT: $($health.dut) | Targets: $($health.targets)"
} catch {
    Write-Host "      Backend not responding yet - check the uvicorn window"
}

# Launch React frontend in new window
Write-Host ""
Write-Host "[2/2] Starting React frontend (npm)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$dashboardDir'; `$env:PATH = [System.Environment]::GetEnvironmentVariable('PATH','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('PATH','User'); npm start"

Write-Host ""
Write-Host "========================================"
Write-Host " Both services starting in new windows"
Write-Host "========================================"
Write-Host ""
Write-Host "  Dashboard : http://localhost:3000"
Write-Host "  Health    : http://localhost:8000/health"
Write-Host ""
Write-Host " Press Ctrl+C in each window to stop"