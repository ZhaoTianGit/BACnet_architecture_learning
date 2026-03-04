"""
================================================================================
 config/settings.py  —  THE SINGLE SOURCE OF TRUTH
================================================================================

 ARCHITECTURE LESSON 1: Configuration Layer
 ─────────────────────────────────────────────
 Rule: NEVER scatter numbers/strings through your code.
 Put ALL settings in ONE place so you only update one file, never hunt
 through hundreds of lines of logic.

 Think of it like a TV remote:
   ❌ Bad:  buttons are glued to the TV in random places
   ✅ Good: all buttons in one remote (this file)

 In industry this is called "12-Factor App" design — config lives separately
 from code, so the same code runs in Dev, Staging, and Production just by
 swapping the config file. No code changes needed.
================================================================================
"""

# =============================================================================
# @dataclass — ARCHITECTURE LESSON: Data Classes
# =============================================================================
# A dataclass is a "blueprint" that groups related settings together.
# Instead of 20 loose variables floating around, you get organised namespaces.
#
# Without dataclass (messy):
#   TARGET_IP   = "192.168.100.183"
#   TARGET_PORT = 63205
#   LOCAL_IP    = "192.168.100.183"
#   LOCAL_PORT  = 47810
#
# With dataclass (organised):
#   dut.ip, dut.port   ← DUT settings live together
#   net.local_ip       ← Network settings live together

"""
================================================================================
 config/settings.py  —  Updated: added PollConfig and PollTarget
================================================================================
 WHAT CHANGED FROM V1:
   + PollTarget dataclass — describes one BACnet object to monitor
   + PollConfig dataclass — polling engine settings (interval, targets, alarms)
   + AppConfig gains a new 'poll' field
================================================================================
"""

from dataclasses import dataclass, field


@dataclass
class DUTConfig:
    ip:              str   = "192.168.100.183"
    port:            int   = 63205            # ⚠ update from Yabe each restart
    device_id:       int   = 3506259
    object_id:       str   = "analog-value,0"
    object_name:     str   = "SetPoint.Value"


@dataclass
class NetworkConfig:
    local_ip:        str   = "192.168.100.183"
    local_port:      int   = 47810
    device_id:       int   = 9999
    device_name:     str   = "PY-Testbench"
    vendor_id:       int   = 999


@dataclass
class TestConfig:
    test_value:      float = 31.0
    write_priority:  int   = 8
    tolerance:       float = 0.01


@dataclass
class TimingConfig:
    socket_bind:     float = 1.0
    post_write:      float = 1.0
    verify_read:     float = 2.0
    restore_buffer:  float = 10.0


# =============================================================================
# NEW — Polling
# =============================================================================

@dataclass
class PollTarget:
    """
    One BACnet object to poll continuously.

    ARCHITECTURE LESSON: Small focused dataclasses over big messy dicts.
    Instead of {"object_id": "analog-value,0", "label": "T Set", ...}
    you get tab-completion, type hints, and clear defaults.
    """
    object_id:   str          = "analog-value,0"
    label:       str          = "Value"
    unit:        str          = ""
    low_alarm:   float | None = None   # alert if value drops below this
    high_alarm:  float | None = None   # alert if value rises above this


@dataclass
class PollConfig:
    """
    Settings for the continuous polling engine.

    ARCHITECTURE LESSON: The 'poll_targets' list is the extension point.
    Add more PollTarget entries to monitor more objects — no code changes needed.
    This is the same plug-and-play principle as hooks, but for data targets.
    """
    interval:        float = 2.0         # seconds between poll cycles
    max_cycles:      int   = 0           # 0 = run forever
    log_to_csv:      bool  = True        # save all readings to CSV
    show_live_table: bool  = True        # Rich live table in terminal
    history_length:  int   = 50          # readings to keep in memory per object

    poll_targets: list = field(default_factory=lambda: [
        # ── Analog Inputs (AI) — read-only sensors ────────────────────────────
        PollTarget(
            object_id  = "analog-input,0",
            label      = "T Indoor",
            unit       = "°C",
            low_alarm  = 15.0,
            high_alarm = 35.0,
        ),
        PollTarget(
            object_id  = "analog-input,1",
            label      = "T Water",
            unit       = "°C",
            low_alarm  = 5.0,
            high_alarm = 60.0,
        ),
        PollTarget(
            object_id  = "analog-input,2",
            label      = "T Outdoor",
            unit       = "°C",
            low_alarm  = -10.0,
            high_alarm = 45.0,
        ),

        # ── Analog Values (AV) — writable setpoints ───────────────────────────
        PollTarget(
            object_id  = "analog-value,0",
            label      = "T Set",
            unit       = "°C",
            low_alarm  = 10.0,
            high_alarm = 40.0,
        ),
        PollTarget(
            object_id  = "analog-value,1",
            label      = "Setpoint 1",
            unit       = "°C",
            low_alarm  = None,
            high_alarm = None,
        ),
        PollTarget(
            object_id  = "analog-value,2",
            label      = "Setpoint 2",
            unit       = "°C",
            low_alarm  = None,
            high_alarm = None,
        ),
        PollTarget(
            object_id  = "analog-value,3",
            label      = "Setpoint 3",
            unit       = "°C",
            low_alarm  = None,
            high_alarm = None,
        ),

        # ── Binary Values (BV) — on/off states ───────────────────────────────
        # No numeric alarms for binary — just monitoring state
        PollTarget(
            object_id  = "binary-value,0",
            label      = "Heater",
            unit       = "",
            low_alarm  = None,
            high_alarm = None,
        ),
        PollTarget(
            object_id  = "binary-value,1",
            label      = "Chiller",
            unit       = "",
            low_alarm  = None,
            high_alarm = None,
        ),

        # ── Multi-State Values (MV) — enumerated modes ────────────────────────
        # Value = integer (1, 2, 3...) representing ventilation level/mode
        PollTarget(
            object_id  = "multi-state-value,0",
            label      = "State",
            unit       = "",
            low_alarm  = None,
            high_alarm = None,
        ),
        PollTarget(
            object_id  = "multi-state-value,1",
            label      = "Vent Level",
            unit       = "",
            low_alarm  = None,
            high_alarm = None,
        ),
    ])


@dataclass
class AppConfig:
    dut:    DUTConfig     = field(default_factory=DUTConfig)
    net:    NetworkConfig = field(default_factory=NetworkConfig)
    test:   TestConfig    = field(default_factory=TestConfig)
    timing: TimingConfig  = field(default_factory=TimingConfig)
    poll:   PollConfig    = field(default_factory=PollConfig)   # ← NEW


cfg = AppConfig()