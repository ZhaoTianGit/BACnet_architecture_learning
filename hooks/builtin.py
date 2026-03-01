"""
================================================================================
 hooks/builtin.py  —  READY-MADE HOOK FUNCTIONS (Plug-and-Play)
================================================================================

 ARCHITECTURE LESSON 6: Plugin System
 ──────────────────────────────────────
 This file contains pre-built hook functions you can plug into the framework.
 None of these are active by default — you choose which ones to enable
 in main.py by registering them.

 Think of this as an "app store" of extensions:
   - You don't install ALL apps, just the ones you need
   - Each app is independent — installing one doesn't affect others
   - You can write your own custom apps (hooks) in the same pattern

 Available hooks in this file:
   📝 log_all_steps       — prints every write/read to console
   📊 csv_reporter        — saves results to a CSV file (audit trail)
   🔔 console_alert       — prints a loud alert on failure
   ⏱  timing_tracker      — measures how long each step takes
   🛡  safety_guard        — blocks writes if DUT is in alarm state

 How to activate (in main.py):
   from hooks.builtin import log_all_steps, csv_reporter
   hooks.register_fn("before_write", log_all_steps)
   hooks.register_fn("on_fail", csv_reporter)

================================================================================
"""

import csv
import logging
import os
from datetime import datetime
from pathlib import Path
from rich import print

log = logging.getLogger("testbench.hooks.builtin")


# =============================================================================
# 📝 HOOK 1: Step Logger
# Fires on: before_write, after_write, before_read, after_read
# Purpose:  prints a structured log line for every network operation
# =============================================================================

async def log_all_steps(ctx: dict) -> None:
    """
    Prints a timestamped log line for every read and write.

    Example output:
      [01:02:03.456] HOOK | BEFORE_WRITE | step=3 | property=present-value | value=31.0
    """
    ts   = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    step = ctx.get("step", "?")
    prop = ctx.get("property", "?")
    val  = ctx.get("value", "")
    pri  = ctx.get("priority", "")

    parts = [f"step={step}", f"property={prop}"]
    if val != "":
        parts.append(f"value={val}")
    if pri != "":
        parts.append(f"priority={pri}")

    print(f"[dim][{ts}] HOOK | {' | '.join(parts)}[/dim]")


# =============================================================================
# 📊 HOOK 2: CSV Audit Reporter
# Fires on: on_pass, on_fail
# Purpose:  appends a result row to a CSV file for audit trail
#
# In industry: every test on live equipment must be logged.
# This hook auto-generates the audit log without touching test logic.
# =============================================================================

CSV_PATH = Path("reports/test_results.csv")

async def csv_reporter(ctx: dict) -> None:
    """
    Appends one row to reports/test_results.csv for every test run.

    CSV columns:
        timestamp, target, object, injected_value, read_back, status, error
    """
    # Create reports folder if it doesn't exist
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

    result     = ctx.get("result")
    target     = ctx.get("target", "unknown")
    obj        = ctx.get("object", "unknown")
    error_msg  = ctx.get("error", "")
    is_new     = not CSV_PATH.exists()

    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Write header row on first run
        if is_new:
            writer.writerow([
                "timestamp", "target", "object",
                "injected_value", "read_back",
                "status", "duration_ms", "error"
            ])

        injected = ""
        read_back = ""
        if result:
            # Extract from TestResult if available
            from config.settings import cfg
            injected  = cfg.test.test_value
            read_back = result.final_value or ""

        writer.writerow([
            datetime.now().isoformat(),
            target,
            obj,
            injected,
            read_back,
            "PASS" if ctx.get("result") and ctx["result"].passed else "FAIL",
            result.duration_ms if result else "",
            error_msg,
        ])

    log.info(f"CSV report appended → {CSV_PATH}")


# =============================================================================
# 🔔 HOOK 3: Console Alert
# Fires on: on_fail
# Purpose:  prints a loud, visible alert when a test fails
# Extend:   replace print() with email/Slack/Teams notification
# =============================================================================

async def console_alert(ctx: dict) -> None:
    """Prints a prominent failure banner with actionable info."""
    error  = ctx.get("error", "unknown error")
    target = ctx.get("target", "unknown")
    result = ctx.get("result")
    steps  = result.steps_done if result else []

    print("\n" + "=" * 60)
    print("🚨  TEST FAILURE ALERT")
    print("=" * 60)
    print(f"  Target  : {target}")
    print(f"  Steps OK: {steps}")
    print(f"  Error   : {error}")
    print(f"  Time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print("  ACTION: Check Yabe → verify Out-Of-Service = False")
    print("=" * 60 + "\n")


# =============================================================================
# ⏱ HOOK 4: Timing Tracker
# Fires on: before_write, after_write, before_read, after_read
# Purpose:  measures how long each step takes — useful for performance testing
# =============================================================================

_step_timings: dict[str, datetime] = {}

async def timing_tracker(ctx: dict) -> None:
    """
    Tracks elapsed time between before_ and after_ hook pairs.

    Prints:
      ⏱ Step 3 | present-value write took 47ms
    """
    step = ctx.get("step", "?")
    prop = ctx.get("property", "?")
    key  = f"{step}_{prop}"

    now = datetime.now()

    if key not in _step_timings:
        # First call (before_write or before_read) — store start time
        _step_timings[key] = now
    else:
        # Second call (after_write or after_read) — compute elapsed
        elapsed_ms = int((now - _step_timings.pop(key)).total_seconds() * 1000)
        print(f"[dim]  ⏱ Step {step} | {prop} took {elapsed_ms}ms[/dim]")


# =============================================================================
# 🛡 HOOK 5: Safety Guard
# Fires on: before_write
# Purpose:  blocks any write if the DUT's status flags indicate an alarm
#
# This is an example of a hook that can PREVENT an action.
# It raises an exception to abort the step — the runner catches it as a failure.
#
# In industry: never inject values into a controller that's already in fault state.
# =============================================================================

BLOCKED_PROPERTIES = set()   # populated by your safety check logic

async def safety_guard(ctx: dict) -> None:
    """
    Example guard hook — extend this with real status-flag checking.

    To block a write, raise an exception:
        raise PermissionError("DUT is in alarm state — write blocked")

    The runner will catch this, mark the test as failed, and still restore OOS.
    """
    prop = ctx.get("property", "")

    # Example: block writing present-value if a safety flag is set externally
    if prop in BLOCKED_PROPERTIES:
        raise PermissionError(
            f"Safety guard blocked write to '{prop}'. "
            f"DUT may be in alarm or fault state. "
            f"Clear BLOCKED_PROPERTIES to proceed."
        )

    # In a real system, you'd read status-flags here and check bit 0 (in-alarm):
    # status = await transport.read(target, obj_id, "status-flags")
    # if status.in_alarm:
    #     raise PermissionError("DUT in alarm — write blocked")


# =============================================================================
# 📦 CONVENIENCE: hook bundles
# =============================================================================
# Pre-grouped sets of hooks for common scenarios.
# Register the whole bundle with one line in main.py.

def register_development_hooks(hooks_manager) -> None:
    """
    Activates hooks suitable for local development and debugging.
    Verbose logging, no file output.
    """
    hooks_manager.register_fn("before_write",  log_all_steps)
    hooks_manager.register_fn("after_write",   log_all_steps)
    hooks_manager.register_fn("before_read",   log_all_steps)
    hooks_manager.register_fn("after_read",    log_all_steps)
    hooks_manager.register_fn("before_write",  timing_tracker)
    hooks_manager.register_fn("after_write",   timing_tracker)
    hooks_manager.register_fn("on_fail",       console_alert)
    log.info("Development hook bundle registered")


def register_production_hooks(hooks_manager) -> None:
    """
    Activates hooks suitable for production / live commissioning.
    CSV audit trail, alerts, safety guard, timing.
    """
    hooks_manager.register_fn("before_write",  safety_guard)
    hooks_manager.register_fn("before_write",  timing_tracker)
    hooks_manager.register_fn("after_write",   timing_tracker)
    hooks_manager.register_fn("before_read",   timing_tracker)
    hooks_manager.register_fn("after_read",    timing_tracker)
    hooks_manager.register_fn("on_pass",       csv_reporter)
    hooks_manager.register_fn("on_fail",       csv_reporter)
    hooks_manager.register_fn("on_fail",       console_alert)
    log.info("Production hook bundle registered")
