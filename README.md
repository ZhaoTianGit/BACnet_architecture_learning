# 🏗️ BACnet Testbench — Modular Framework

<div align="center">

![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)
![Protocol](https://img.shields.io/badge/Protocol-BACnet%2FIP-green.svg)
![Library](https://img.shields.io/badge/Library-bacpypes3-orange.svg)
![Architecture](https://img.shields.io/badge/Architecture-Modular-purple.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)
![Status](https://img.shields.io/badge/Status-Working-brightgreen.svg)

**A plug-and-play BACnet/IP automation testbench built with hooks, dependency injection, and layered architecture.**

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [Pre-Flight Requirements](#-pre-flight-requirements)
- [Installation](#-installation)
- [Before Every Run](#-before-every-run-checklist)
- [Running the Framework](#-running-the-framework)
- [Expected Output](#-expected-output)
- [Configuration](#-configuration)
- [Extending with Hooks](#-extending-with-hooks)
- [Project Structure](#-project-structure)
- [Troubleshooting](#-troubleshooting)

---

## 📌 Overview

This framework automates the BACnet **Out-Of-Service override test sequence** — the industry-standard method for injecting test vectors into a controller without physical hardware.

> **Validated against:** RoomController.Simulator (Device ID: 3506259)  
> `SetPoint.Value (AV:0)` successfully written to `31.0 °C` ✅

The 4-step sequence it automates:

```
Step 1 ──► Write  out-of-service = True        # decouple hardware input
Step 2 ──► Read   out-of-service               # verify Step 1 landed
Step 3 ──► Write  present-value = 31.0 @ P8   # inject test vector
Step 4 ──► Read   present-value               # verify Step 3 landed
           Wait   10s buffer                  # observe in Yabe
           Write  out-of-service = False       # ALWAYS restore
```

---

## 🏗️ Architecture

```
BACnet_architecture_learning/
│
├── main.py                  ← Entry point — wires all components together
│
├── config/
│   └── settings.py          ← ALL settings in one place (DUT, network, test, timing)
│
├── core/
│   ├── hooks.py             ← Event bus — plug in custom behaviour at named slots
│   ├── transport.py         ← Network layer — wraps bacpypes3 with clean interface
│   └── runner.py            ← Orchestrator — coordinates the 4-step test sequence
│
└── hooks/
    └── builtin.py           ← Ready-made extensions (CSV logger, timing, alerts)
```

| Layer | File | Responsibility |
|-------|------|---------------|
| Config | `settings.py` | Single source of truth for all values |
| Network | `transport.py` | BACnet packet send/receive only |
| Logic | `runner.py` | Test step coordination only |
| Events | `hooks.py` | Notify extensions at key moments |
| Extensions | `builtin.py` | Optional plug-in features |

---

## ✅ Pre-Flight Requirements

### 1 — Python 3.13+

Download from [python.org](https://www.python.org/downloads/).  
Verify in terminal:
```powershell
python --version
# Expected: Python 3.13.x
```

---

### 2 — Install Dependencies

```powershell
pip install bacpypes3 BAC0 rich
```

Verify:
```powershell
pip show bacpypes3 | Select-String "Version"
pip show BAC0      | Select-String "Version"
pip show rich      | Select-String "Version"
```

---

### 3 — Windows Firewall — Open BACnet UDP Ports (One-Time Setup)

> Run PowerShell **as Administrator** (`Win+X` → Windows Terminal (Admin))

```powershell
New-NetFirewallRule -DisplayName "BACnet IN"  -Direction Inbound  -Protocol UDP -LocalPort 47808,47810 -Action Allow
New-NetFirewallRule -DisplayName "BACnet OUT" -Direction Outbound -Protocol UDP -LocalPort 47808,47810 -Action Allow
New-NetFirewallRule -DisplayName "BACnet Sim" -Direction Inbound  -Protocol UDP -RemoteAddress 192.168.100.183 -Action Allow
```

> **Why:** Windows Firewall allows ICMP (ping) but blocks UDP by default.
> BACnet runs over UDP — without these rules, packets are silently dropped.

---

### 4 — Verify Network Reachability

```powershell
ping 192.168.100.183
```

All 4 replies must succeed before running the testbench.

---

### 5 — Install & Launch Yabe (BACnet Explorer)

Download: [Yabe on SourceForge](https://sourceforge.net/projects/yetanotherbacnetexplorer/)

Launch Yabe → you should see your simulator device appear:
<img width="1909" height="1019" alt="image" src="https://github.com/user-attachments/assets/265a9f6e-11bf-46cf-be51-0fa9cc31bbce" />

```
Network View
└── Udp:47808
    └── RoomController.Simulator [3506259]
```

---

## 📦 Installation

### 1 — Clone / Download the project

```powershell
git clone <your-repo-url>
cd BACnet_architecture_learning
```

### 2 — Create Python package marker files

```powershell
New-Item config\__init__.py -Force
New-Item core\__init__.py   -Force
New-Item hooks\__init__.py  -Force
```

> **Why:** Python requires `__init__.py` in every subfolder to treat it as an importable package.

### 3 — Verify structure

```powershell
tree /F
```

Expected:
```
BACnet_architecture_learning/
├── main.py
├── config/
│   ├── __init__.py
│   └── settings.py
├── core/
│   ├── __init__.py
│   ├── hooks.py
│   ├── transport.py
│   └── runner.py
└── hooks/
    ├── __init__.py
    └── builtin.py
```

---

## 🔧 Before Every Run — Checklist

> The simulator assigns a **new dynamic port every time it restarts**.  
> You must update the port in config before each run.

```
 □  Start the Room Control Simulator
 □  Open Yabe — confirm device 3506259 is visible
 □  Hover over the device in Yabe's left panel → note the current port
     Example: RoomController.Simulator → 192.168.100.183:53752
 □  Update TARGET_PORT in main.py:
     cfg.dut.port = 53752    ← replace with current port from Yabe
 □  Confirm Out-Of-Service = False in Yabe Properties panel
 □  Confirm Status Flags = 0000 in Yabe Properties panel
 □  Run: ping 192.168.100.183  (all 4 replies must succeed)
```

---

## 🚀 Running the Framework

Always run from the project root using the terminal — **not** the VSCode play button:

```powershell
cd <your_folder_path> <-- make sure you are in the path of your folder
python main.py
```

> **Tip:** If VSCode's Code Runner extension runs a `tempCodeRunnerFile.py` instead,
> always use the integrated terminal (`Ctrl+\``) and type `python main.py` directly.

---

## 📊 Expected Output

A successful run looks like this:
<img width="969" height="1078" alt="image" src="https://github.com/user-attachments/assets/c0053591-e136-4581-bb6b-3c1b59a10ecd" />

---

## ⚙️ Configuration

All settings live in **`config/settings.py`**. For day-to-day use, only edit the `configure()` function in `main.py`:

```python
def configure() -> AppConfig:
    cfg.dut.port        = 53752   # ⚠ update from Yabe after every restart
    cfg.test.test_value = 31.0    # °C — value to inject
    cfg.dut.object_id   = "analog-value,0"   # target object
    return cfg
```

### Full Config Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `cfg.dut.ip` | `192.168.100.183` | DUT IP address |
| `cfg.dut.port` | `63205` | ⚠ Dynamic — update from Yabe |
| `cfg.dut.object_id` | `analog-value,0` | BACnet object to test |
| `cfg.test.test_value` | `31.0` | Value to inject (°C) |
| `cfg.test.write_priority` | `8` | BACnet priority (8 = Manual Operator) |
| `cfg.timing.restore_buffer` | `10.0` | Seconds to wait before restoring OOS |
| `cfg.timing.post_write` | `1.0` | Seconds between write and next step |
| `cfg.net.local_port` | `47810` | Python testbench UDP port |

---

## 🔌 Extending with Hooks

The hook system lets you add features **without editing core logic**.  
Register hook functions in `main.py`'s `register_hooks()`:

```python
def register_hooks() -> None:
    # Development mode — verbose logging, no file output
    register_development_hooks(hooks)

    # Production mode — CSV audit trail, safety guard, alerts
    # register_production_hooks(hooks)
```

### Available Hook Slots

| Slot | When It Fires |
|------|--------------|
| `before_write` | Just before any WriteProperty call |
| `after_write` | After a successful write |
| `before_read` | Just before any ReadProperty call |
| `after_read` | After a successful read |
| `on_pass` | When all 4 steps complete successfully |
| `on_fail` | When any step throws an exception |
| `on_restore` | After Out-Of-Service is restored |

### Write Your Own Hook

```python
# In main.py — register_hooks()
@hooks.register("on_pass")
async def my_custom_hook(ctx):
    print(f"Test passed! Value = {ctx['result'].final_value}")
```

No other files need to change.

---

## 🐛 Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: config` | Running from wrong directory | `cd` into `BACnet_architecture_learning` first |
| `SyntaxError: utf-8 codec can't decode` | `__init__.py` saved as UTF-16 by PowerShell | Recreate with `New-Item config\__init__.py -Force` |
| Rich tags printed as `[bold green]...[/bold green]` | Missing `from rich import print` in that file | Add `from rich import print` to every `.py` that uses markup |
| `tempCodeRunnerFile.py` runs instead of `main.py` | VSCode Code Runner extension | Use terminal: `python main.py` |
| `AbortPDU: no-response` | Port changed since last Yabe check | Update `cfg.dut.port` in `main.py` |
| `Pre-flight: out-of-service already True` | Previous run didn't restore OOS | Manually write OOS=False in Yabe, then re-run |
| Ping works but writes fail | Windows Firewall blocking UDP | Run the `New-NetFirewallRule` commands in Admin PowerShell |

---

## 🤝 Acknowledgements

Built with help from AI pair programming:

| Assistant | Role |
|-----------|------|
| 🤖 [Claude](https://claude.ai) (Anthropic) | Architecture design, debug partner, code review |
| 🤖 [Gemini](https://gemini.google.com) (Google) | BACnet protocol reference |

---

<div align="center">

**14 debug iterations · 1 working testbench · infinite lessons learned** 🎉

</div>
