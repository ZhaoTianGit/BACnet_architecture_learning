# setup_once.ps1 - Run ONE TIME to configure the environment permanently

Write-Host "========================================"
Write-Host " BACnet Dashboard - One-Time Setup"
Write-Host "========================================"

# 1. Fix PowerShell execution policy
Write-Host ""
Write-Host "[1/5] Setting PowerShell execution policy..."
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
Write-Host "      Done."

# 2. Add Node.js to PATH permanently
Write-Host ""
Write-Host "[2/5] Adding Node.js to PATH..."
$nodePath = "C:\Program Files\nodejs"
$currentPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
if ($currentPath -notlike "*nodejs*") {
    [System.Environment]::SetEnvironmentVariable("PATH", $currentPath + ";" + $nodePath, "User")
    Write-Host "      Node.js path added."
} else {
    Write-Host "      Node.js already in PATH."
}
$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","User")

# 3. Install Python dependencies
Write-Host ""
Write-Host "[3/5] Installing Python dependencies..."
pip install "uvicorn[standard]" fastapi websockets bacpypes3 rich --quiet
Write-Host "      Done."

# 4. Install React dependencies
Write-Host ""
Write-Host "[4/5] Installing React dependencies..."
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$dashboardPath = Join-Path $scriptDir "bacnet-dashboard"

if (Test-Path $dashboardPath) {
    Push-Location $dashboardPath
    npm install --silent
    Pop-Location
    Write-Host "      Done."
} else {
    Write-Host "      bacnet-dashboard folder not found - creating React app..."
    Push-Location $scriptDir
    npx create-react-app bacnet-dashboard
    Pop-Location
    Write-Host "      Done. Remember to paste your App.js and index.js!"
}

# 5. Verify everything
Write-Host ""
Write-Host "[5/5] Verifying installation..."
Write-Host "      node:    $(node -v)"
Write-Host "      npm:     $(npm -v)"
Write-Host "      python:  $(python --version)"
Write-Host "      uvicorn: $(uvicorn --version)"

Write-Host ""
Write-Host "========================================"
Write-Host " Setup complete! Run .\start.ps1 to launch"
Write-Host "========================================"