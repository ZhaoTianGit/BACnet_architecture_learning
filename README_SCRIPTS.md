# BACnet Dashboard — Startup Scripts

## First Time Ever (Fresh Windows Machine)

Before anything else, run this ONE LINE in PowerShell to unlock script execution:

```powershell
Unblock-File -Path .\setup_once.ps1
Unblock-File -Path .\start.ps1
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
```

Then proceed with the setup below.

---

## Two scripts, two purposes

### `setup_once.ps1` — Run ONCE after fresh install
Fixes everything permanently:
- Sets PowerShell execution policy
- Adds Node.js to PATH forever
- Installs all Python packages (`uvicorn[standard]`, `fastapi`, `websockets`, etc.)
- Installs React npm packages

```powershell
.\setup_once.ps1
```

### `start.ps1` — Run EVERY SESSION
Launches everything in one click:
- Opens uvicorn backend in its own window
- Opens React frontend in its own window
- Checks backend health automatically
- Reminds you to update the DUT port

```powershell
.\start.ps1
```

---

## File placement

Put both scripts in your project root:

```
BACnet_architecture_learning/
├── start.ps1             ← daily launcher
├── setup_once.ps1        ← one-time setup
├── README_SCRIPTS.md     ← this file
├── api_server.py
├── main.py
├── main_poll.py
├── main_cov.py
├── config/
├── core/
├── hooks/
└── bacnet-dashboard/
```

---

## Every Session Checklist

```
□ 1. Open Yabe + start RoomController.Simulator
□ 2. Note the new DUT port from Yabe
□ 3. Update cfg.dut.port in api_server.py
□ 4. Run .\start.ps1
□ 5. Open http://localhost:3000
```

Verify connection at: http://localhost:8000/health
Expected: `{"status":"ok","clients":1,"dut":"192.168.x.x:XXXXX","targets":11}`

`clients:1` = browser connected ✅
`clients:0` = browser not connected yet ❌

---

## VSCode Integration (Optional)

Add this to `.vscode/tasks.json` to launch with a keyboard shortcut:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Launch BACnet Dashboard",
      "type": "shell",
      "command": ".\\start.ps1",
      "group": {
        "kind": "build",
        "isDefault": true
      },
      "presentation": {
        "reveal": "always",
        "panel": "new"
      }
    }
  ]
}
```

Then press `Ctrl+Shift+B` to launch everything without touching the terminal.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `npm not recognized` | Run `.\start.ps1` — it reloads PATH automatically |
| `uvicorn[standard]` not installed | Run `pip install "uvicorn[standard]"` |
| WebSocket 404 / No supported WebSocket library | Run `pip install "uvicorn[standard]"` |
| Dashboard shows DISCONNECTED | Check `http://localhost:8000/health` — if clients=0, refresh browser |
| BACnet no-response / AbortPDU | Yabe port changed — update `cfg.dut.port` in `api_server.py` |
| Script cannot be loaded (unsigned) | Run `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force` first |