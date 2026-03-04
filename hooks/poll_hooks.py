"""
================================================================================
 hooks/poll_hooks.py  —  READY-MADE HOOKS FOR THE POLLER
================================================================================
 Three new hook slots:
   "on_poll"    → every cycle
   "on_change"  → only when value differs from previous reading
   "on_alarm"   → when value crosses a low/high threshold
================================================================================
"""

import logging
from datetime import datetime
from rich import print

log = logging.getLogger("testbench.poll_hooks")


async def log_on_change(ctx: dict) -> None:
    """Prints a line only when a value changes — ignores stable readings."""
    reading = ctx.get("reading")
    prev    = ctx.get("prev_value")
    delta   = ctx.get("delta", 0)
    ts      = datetime.now().strftime("%H:%M:%S")

    direction = "↑" if delta > 0 else "↓"
    colour    = "yellow" if delta > 0 else "cyan"

    print(
        f"[dim][{ts}][/dim] "
        f"[bold]CHANGE[/bold] | "
        f"[bold white]{reading.label}[/bold white] | "
        f"[dim]{prev:.2f}[/dim] → "
        f"[bold {colour}]{reading.value_str}[/bold {colour}] "
        f"[dim](Δ {direction}{abs(delta):.2f})[/dim]"
    )


async def alarm_alert(ctx: dict) -> None:
    """Loud banner when a threshold is crossed. Extend with email/Slack here."""
    reading = ctx.get("reading")
    target  = ctx.get("target")
    ts      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n[bold white on red]{'─'*50}[/bold white on red]")
    print(f"[bold white on red]  🚨 ALARM: {reading.label} OUT OF RANGE  [/bold white on red]")
    print(f"[bold white on red]{'─'*50}[/bold white on red]")
    print(f"[red]  Object  : {reading.object_id}[/red]")
    print(f"[red]  Value   : {reading.value_str}[/red]")
    if target.low_alarm is not None:
        print(f"[red]  Low  limit : {target.low_alarm} {target.unit}[/red]")
    if target.high_alarm is not None:
        print(f"[red]  High limit : {target.high_alarm} {target.unit}[/red]")
    print(f"[red]  Time    : {ts}[/red]")
    print(f"[bold white on red]{'─'*50}[/bold white on red]\n")


async def heartbeat(ctx: dict) -> None:
    """Prints a dot every 10 cycles so you know the poller is alive."""
    cycle = ctx.get("cycle", 0)
    if cycle % 10 == 0:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[dim][{ts}] ♥ heartbeat — cycle {cycle}[/dim]")


def register_poll_hooks(hooks_manager) -> None:
    """Register the default polling hook bundle."""
    hooks_manager.register_fn("on_change", log_on_change)
    hooks_manager.register_fn("on_alarm",  alarm_alert)
    log.info("Poll hook bundle registered")