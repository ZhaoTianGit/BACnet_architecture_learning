"""
================================================================================
 hooks/cov_hooks.py  —  READY-MADE HOOKS FOR THE COV MONITOR
================================================================================
 Three new hook slots introduced by COVMonitor:

   "on_cov"        → every notification received (any object, any value)
   "on_cov_change" → only when value differs from last known value
   "on_cov_alarm"  → when value crosses a low/high threshold

 These mirror the polling hooks (on_poll, on_change, on_alarm) intentionally.
 Same mental model, different transport mechanism underneath.
================================================================================
"""

import logging
from datetime import datetime
from rich import print

log = logging.getLogger("testbench.cov_hooks")


async def log_cov_change(ctx: dict) -> None:
    """
    Logs a line for every value change notification.
    COV already filters — this only fires when value actually differs.
    """
    notif  = ctx.get("notification")
    prev   = ctx.get("prev_value")
    delta  = ctx.get("delta", 0)
    ts     = datetime.now().strftime("%H:%M:%S")

    direction = "↑" if delta > 0 else "↓"
    colour    = "yellow" if delta > 0 else "cyan"

    print(
        f"[dim][{ts}][/dim] "
        f"[bold magenta]COV[/bold magenta] | "
        f"[bold white]{notif.label}[/bold white] | "
        f"[dim]{prev:.2f}[/dim] → "
        f"[bold {colour}]{notif.value_str}[/bold {colour}] "
        f"[dim](Δ {direction}{abs(delta):.2f})[/dim]"
    )


async def log_all_cov(ctx: dict) -> None:
    """
    Logs EVERY notification including unchanged values.
    Useful for debugging — confirms the DUT is sending notifications.
    """
    notif = ctx.get("notification")
    ts    = datetime.now().strftime("%H:%M:%S")
    print(
        f"[dim][{ts}] COV RECV | {notif.label} ({notif.object_id}) = {notif.value_str}[/dim]"
    )


async def cov_alarm_alert(ctx: dict) -> None:
    """Loud alarm banner when a COV threshold is crossed."""
    notif  = ctx.get("notification")
    target = ctx.get("target")
    ts     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n[bold white on red]{'─'*50}[/bold white on red]")
    print(f"[bold white on red]  🚨 COV ALARM: {notif.label} OUT OF RANGE  [/bold white on red]")
    print(f"[bold white on red]{'─'*50}[/bold white on red]")
    print(f"[red]  Object  : {notif.object_id}[/red]")
    print(f"[red]  Value   : {notif.value_str}[/red]")
    if target.low_alarm is not None:
        print(f"[red]  Low  limit : {target.low_alarm} {target.unit}[/red]")
    if target.high_alarm is not None:
        print(f"[red]  High limit : {target.high_alarm} {target.unit}[/red]")
    print(f"[red]  Time    : {ts}[/red]")
    print(f"[bold white on red]{'─'*50}[/bold white on red]\n")


def register_cov_hooks(hooks_manager) -> None:
    """Register the default COV hook bundle."""
    hooks_manager.register_fn("on_cov_change", log_cov_change)
    hooks_manager.register_fn("on_cov_alarm",  cov_alarm_alert)
    log.info("COV hook bundle registered")
