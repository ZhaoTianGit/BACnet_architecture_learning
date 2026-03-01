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

from dataclasses import dataclass, field


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

@dataclass
class DUTConfig:
    """
    DUT = Device Under Test.
    Everything that describes the target BACnet device.
    ⚠ Update 'port' every time Yabe/simulator restarts.
    """
    ip:              str   = "192.168.100.183"
    port:            int   = 63205            # ⚠ dynamic — check Yabe each run
    device_id:       int   = 3506259
    object_id:       str   = "analog-value,0" # AV:0 = SetPoint.Value
    object_name:     str   = "SetPoint.Value"


@dataclass
class NetworkConfig:
    """
    Local testbench network settings.
    Use explicit NIC IP, not 0.0.0.0, to control routing on multi-NIC servers.
    """
    local_ip:        str   = "192.168.100.183"
    local_port:      int   = 47810
    device_id:       int   = 9999
    device_name:     str   = "PY-Testbench"
    vendor_id:       int   = 999


@dataclass
class TestConfig:
    """
    What to inject and how.
    """
    test_value:      float = 31.0   # °C — the value to inject
    write_priority:  int   = 8      # 8 = Manual Operator (ASHRAE standard)
    tolerance:       float = 0.01   # float comparison delta


@dataclass
class TimingConfig:
    """
    All sleep/delay values in one place.
    In a fast CI/CD pipeline you can reduce these to speed up test runs.
    """
    socket_bind:     float = 1.0  # wait for OS to bind UDP socket
    post_write:      float = 1.0  # wait for controller to process write
    verify_read:     float = 2.0  # wait before read-back
    restore_buffer:  float = 10.0 # wait before restoring original value (in case of failure)

@dataclass
class AppConfig:
    """
    MASTER CONFIG — the one object you pass around the whole app.
    Composes all sub-configs into one clean package.
    """
    dut:     DUTConfig     = field(default_factory=DUTConfig)
    net:     NetworkConfig = field(default_factory=NetworkConfig)
    test:    TestConfig    = field(default_factory=TestConfig)
    timing:  TimingConfig  = field(default_factory=TimingConfig)


# =============================================================================
# The one config instance the whole app uses
# =============================================================================
# Import this anywhere with:  from config.settings import cfg
cfg = AppConfig()
