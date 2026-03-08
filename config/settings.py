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

"""
================================================================================
 config/settings.py  —  Updated: added COVConfig and COVTarget
================================================================================
 WHAT CHANGED FROM V2:
   + COVTarget  — describes one BACnet object to subscribe to via COV
   + COVConfig  — COV engine settings (lifetime, resubscribe, targets)
================================================================================
"""

from dataclasses import dataclass, field


@dataclass
class DUTConfig:
    ip:          str = "192.168.100.183"
    port:        int = 0    # `0` means **"no default — caller must provide this"**. It's a deliberate sentinel value that forces every entry point to explicitly set the port.
    device_id:   int = 3506259
    object_id:   str = "analog-value,0"
    object_name: str = "SetPoint.Value"

def __post_init__(self):
    if self.port == 0:
        raise ValueError(
            "DUT port not configured. "
            "Set cfg.dut.port in your entry point (main_cov.py, api_server.py etc.)"
        )
@dataclass
class NetworkConfig:
    local_ip:    str = "192.168.100.183"
    local_port:  int = 47810
    device_id:   int = 9999
    device_name: str = "PY-Testbench"
    vendor_id:   int = 999


@dataclass
class TestConfig:
    test_value:     float = 31.0
    write_priority: int   = 8
    tolerance:      float = 0.01


@dataclass
class TimingConfig:
    socket_bind:    float = 1.0
    post_write:     float = 1.0
    verify_read:    float = 2.0
    restore_buffer: float = 10.0


@dataclass
class PollTarget:
    object_id:  str          = "analog-value,0"
    label:      str          = "Value"
    unit:       str          = ""
    low_alarm:  float | None = None
    high_alarm: float | None = None


@dataclass
class PollConfig:
    interval:        float = 2.0
    max_cycles:      int   = 0
    log_to_csv:      bool  = True
    show_live_table: bool  = True
    history_length:  int   = 50

    poll_targets: list = field(default_factory=lambda: [
        PollTarget(object_id="analog-input,0",       label="T Indoor",   unit="°C",  low_alarm=15.0,  high_alarm=35.0),
        PollTarget(object_id="analog-input,1",       label="T Water",    unit="°C",  low_alarm=5.0,   high_alarm=60.0),
        PollTarget(object_id="analog-input,2",       label="T Outdoor",  unit="°C",  low_alarm=-10.0, high_alarm=45.0),
        PollTarget(object_id="analog-value,0",       label="T Set",      unit="°C",  low_alarm=10.0,  high_alarm=40.0),
        PollTarget(object_id="analog-value,1",       label="Setpoint 1", unit="°C"),
        PollTarget(object_id="analog-value,2",       label="Setpoint 2", unit="°C"),
        PollTarget(object_id="analog-value,3",       label="Setpoint 3", unit="°C"),
        PollTarget(object_id="binary-value,0",       label="Heater",     unit=""),
        PollTarget(object_id="binary-value,1",       label="Chiller",    unit=""),
        PollTarget(object_id="multi-state-value,0",  label="State",      unit=""),
        PollTarget(object_id="multi-state-value,1",  label="Vent Level", unit=""),
    ])


# =============================================================================
# NEW — COV (Change of Value) Configuration
# =============================================================================

@dataclass
class COVTarget:
    """
    One BACnet object to subscribe to via COV.

    ARCHITECTURE NOTE:
    COV is push-based — the DUT sends notifications to us only when the
    value changes. No polling needed. Network traffic drops to near zero
    when values are stable.

    Args:
        object_id:        BACnet object e.g. "analog-input,0"
        label:            Human-readable name for display and logging
        unit:             Engineering unit string e.g. "°C"
        low_alarm:        Alert threshold — fires on_cov_alarm hook
        high_alarm:       Alert threshold — fires on_cov_alarm hook
        confirmed:        True = DUT ACKs every notification (reliable but
                          more traffic). False = fire-and-forget (lighter).
                          Use True for critical values in production.
    """
    object_id:  str          = "analog-value,0"
    label:      str          = "Value"
    unit:       str          = ""
    low_alarm:  float | None = None
    high_alarm: float | None = None
    confirmed:  bool         = False   # unconfirmed = lighter traffic


@dataclass
class COVConfig:
    """
    Settings for the COV monitoring engine.

    ARCHITECTURE LESSON: Push vs Pull
    ──────────────────────────────────
    Polling (Pull):
      Client asks "what's the value?" every N seconds.
      Network traffic = constant, regardless of how often values change.

    COV (Push):
      Client subscribes once. Server sends update ONLY when value changes.
      Network traffic = proportional to rate of change.
      Stable values = near zero traffic.
      Fast-changing values = more traffic, but only when needed.

    For a data center with 10,000 BACnet points:
      Polling all at 2s = 5,000 packets/second constantly
      COV all          = near zero when stable, bursts during events
    """
    lifetime:          int   = 300    # subscription lifetime in seconds
                                      # DUT drops subscription after this
                                      # We resubscribe at 80% of lifetime
    resubscribe_margin: float = 0.8   # resubscribe at 80% of lifetime
    log_to_csv:        bool  = True
    show_live_table:   bool  = True
    process_id:        int   = 1      # local identifier for this subscription

    cov_targets: list = field(default_factory=lambda: [
        # ── Analog Inputs — temperature sensors ───────────────────────────
        COVTarget(object_id="analog-input,0",      label="T Indoor",   unit="°C",  low_alarm=15.0,  high_alarm=35.0),
        COVTarget(object_id="analog-input,1",      label="T Water",    unit="°C",  low_alarm=5.0,   high_alarm=60.0),
        COVTarget(object_id="analog-input,2",      label="T Outdoor",  unit="°C",  low_alarm=-10.0, high_alarm=45.0),

        # ── Analog Values — setpoints ─────────────────────────────────────
        COVTarget(object_id="analog-value,0",      label="T Set",      unit="°C",  low_alarm=10.0,  high_alarm=40.0),
        COVTarget(object_id="analog-value,1",      label="Setpoint 1", unit="°C"),
        COVTarget(object_id="analog-value,2",      label="Setpoint 2", unit="°C"),
        COVTarget(object_id="analog-value,3",      label="Setpoint 3", unit="°C"),

        # ── Binary Values — on/off states ─────────────────────────────────
        # confirmed=True for critical equipment states
        COVTarget(object_id="binary-value,0",      label="Heater",     unit="",    confirmed=True),
        COVTarget(object_id="binary-value,1",      label="Chiller",    unit="",    confirmed=True),

        # ── Multi-State Values ────────────────────────────────────────────
        COVTarget(object_id="multi-state-value,0", label="State",      unit=""),
        COVTarget(object_id="multi-state-value,1", label="Vent Level", unit=""),
    ])


@dataclass
class AppConfig:
    dut:    DUTConfig    = field(default_factory=DUTConfig)
    net:    NetworkConfig = field(default_factory=NetworkConfig)
    test:   TestConfig   = field(default_factory=TestConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    poll:   PollConfig   = field(default_factory=PollConfig)
    cov:    COVConfig    = field(default_factory=COVConfig)    # ← NEW


cfg = AppConfig()