"""
================================================================================
 core/poller.py  —  THE CONTINUOUS POLLING ENGINE
================================================================================

 ARCHITECTURE LESSON: How Polling Extends the Existing Framework
 ────────────────────────────────────────────────────────────────
 The Poller reuses the SAME BACnetTransport from transport.py.
 It doesn't re-implement any network code — it just calls transport.read()
 repeatedly on a timer.

 This is the power of the layered architecture you built:
   TestRunner  uses transport.write() + transport.read()  → one-shot test
   Poller      uses transport.read() in a loop            → continuous monitoring

 Same transport, two completely different behaviours on top of it.

 NEW HOOK SLOTS added for polling:
   "on_poll"      → fires after every successful read cycle
   "on_change"    → fires when a value changes from the previous reading
   "on_alarm"     → fires when a value crosses a low/high threshold

================================================================================
"""

import asyncio
import csv
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from rich import print
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

log = logging.getLogger("testbench.poller")
console = Console()


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PollReading:
    """
    One snapshot reading of one BACnet object at one moment in time.

    ARCHITECTURE LESSON: Value Object
    This tiny immutable record is the fundamental unit of data.
    We store a list of these — never raw floats — so we always
    know WHEN a reading was taken, not just WHAT the value was.
    """
    timestamp:  datetime
    object_id:  str
    label:      str
    value:      float | bool | str | None
    unit:       str
    in_alarm:   bool = False
    error:      str  = ""

    @property
    def value_str(self) -> str:
        """Formatted value string for display."""
        if self.error:
            return f"ERROR: {self.error}"
        if self.value is None:
            return "—"
        if isinstance(self.value, bool):
            return "True" if self.value else "False"
        try:
            return f"{float(self.value):.2f} {self.unit}".strip()
        except (TypeError, ValueError):
            return str(self.value)


@dataclass
class PollState:
    """
    Running state for one polled object — tracks history and change detection.

    ARCHITECTURE LESSON: Encapsulated State
    Instead of a messy dict {"prev_value": x, "history": [], "alarm": False},
    we group it into a clean class. One PollState per polled object.
    """
    target:       object
    history:      deque = field(default_factory=lambda: deque(maxlen=50))
    prev_value:   float | None = None
    alarm_active: bool  = False
    total_reads:  int   = 0
    error_count:  int   = 0

    def push(self, reading: PollReading) -> None:
        self.history.append(reading)
        self.total_reads += 1
        if reading.error:
            self.error_count += 1

    @property
    def latest(self) -> PollReading | None:
        return self.history[-1] if self.history else None

    @property
    def latest_value(self) -> float | None:
        r = self.latest
        if r and not r.error:
            try:
                return float(r.value)
            except (TypeError, ValueError):
                return None
        return None


# =============================================================================
# THE POLLER
# =============================================================================

class Poller:
    """
    Continuously polls one or more BACnet objects and:
      - Displays a live Rich table in the terminal
      - Logs all readings to CSV
      - Fires hooks on poll, value change, and threshold alarms
      - Runs until max_cycles is reached or Ctrl+C is pressed

    Usage:
        async with BACnetTransport(cfg.net) as transport:
            poller = Poller(cfg, transport, hooks)
            await poller.run()
    """

    def __init__(self, cfg, transport, hooks):
        self._cfg       = cfg
        self._transport = transport
        self._hooks     = hooks
        self._poll_cfg  = cfg.poll
        self._dut_ip    = cfg.dut.ip
        self._dut_port  = cfg.dut.port

        # Build one PollState per target
        self._states: dict[str, PollState] = {
            t.object_id: PollState(
                target  = t,
                history = deque(maxlen=self._poll_cfg.history_length)
            )
            for t in self._poll_cfg.poll_targets
        }

        self._cycle                  = 0
        self._running                = False
        self._csv_path               = Path("reports/poll_log.csv")
        self._csv_headers_written    = False

        from bacpypes3.pdu import Address
        self._target_addr = Address(f"{self._dut_ip}:{self._dut_port}")

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    async def run(self) -> None:
        """
        Start the polling loop.
        Runs until max_cycles is reached (0 = forever) or Ctrl+C is pressed.
        """
        self._running = True
        max_c = self._poll_cfg.max_cycles

        print(f"\n[bold cyan]{'─'*60}[/bold cyan]")
        print(f"[bold cyan] Continuous Poller Starting[/bold cyan]")
        print(f"[bold cyan] DUT      : {self._dut_ip}:{self._dut_port}[/bold cyan]")
        print(f"[bold cyan] Interval : {self._poll_cfg.interval}s[/bold cyan]")
        print(f"[bold cyan] Targets  : {len(self._states)} object(s)[/bold cyan]")
        cycles_label = "∞ (until Ctrl+C)" if max_c == 0 else str(max_c)
        print(f"[bold cyan] Cycles   : {cycles_label}[/bold cyan]")
        print(f"[bold cyan]{'─'*60}[/bold cyan]\n")
        print("[dim]Press Ctrl+C to stop polling gracefully.[/dim]\n")

        if self._poll_cfg.log_to_csv:
            self._csv_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if self._poll_cfg.show_live_table:
                await self._run_with_live_table(max_c)
            else:
                await self._run_plain(max_c)

        except KeyboardInterrupt:
            print("\n[yellow]Polling stopped by user (Ctrl+C)[/yellow]")
        finally:
            self._running = False
            self._print_summary()

    # =========================================================================
    # INNER LOOPS
    # =========================================================================

    async def _run_with_live_table(self, max_c: int) -> None:
        """
        Polling loop with a Rich Live table that refreshes in-place.

        ARCHITECTURE LESSON: Rich Live
        Rich's Live context manager redraws the same table in-place instead
        of printing new lines every cycle. This gives a clean dashboard feel.
        """
        with Live(self._build_table(), refresh_per_second=2, console=console) as live:
            while self._running:
                await self._poll_cycle()
                live.update(self._build_table())

                if max_c > 0 and self._cycle >= max_c:
                    break

                await asyncio.sleep(self._poll_cfg.interval)

    async def _run_plain(self, max_c: int) -> None:
        """Polling loop without live table — prints each reading as a new line."""
        while self._running:
            await self._poll_cycle()
            self._print_plain_cycle()

            if max_c > 0 and self._cycle >= max_c:
                break

            await asyncio.sleep(self._poll_cfg.interval)

    # =========================================================================
    # ONE POLL CYCLE
    # =========================================================================

    async def _poll_cycle(self) -> None:
        """
        Read ALL targets concurrently in one cycle, then process results.

        ARCHITECTURE LESSON: asyncio.gather() — Concurrent Reads
        ─────────────────────────────────────────────────────────
        Without gather (sequential — slow):
            for target in targets:
                value = await transport.read(target)   # waits for each one
            # 5 targets × 1s each = 5 seconds per cycle

        With gather (concurrent — fast):
            results = await asyncio.gather(*[transport.read(t) for t in targets])
            # All 5 fire simultaneously → still only ~1 second per cycle

        gather() = "start all of these at the same time, wait for all to finish."
        Essential for polling many points across a data center floor.
        """
        self._cycle += 1
        ts = datetime.now()

        tasks = [
            self._read_one(state, ts)
            for state in self._states.values()
        ]
        readings: list[PollReading] = await asyncio.gather(*tasks)

        for reading in readings:
            state = self._states[reading.object_id]
            prev  = state.latest_value
            state.push(reading)

            # ── Hook: on_poll — fires every cycle ────────────────────────────
            await self._hooks.trigger("on_poll", {
                "cycle":   self._cycle,
                "reading": reading,
            })

            # ── Hook: on_change — fires only when value changes ───────────────
            curr = state.latest_value
            if prev is not None and curr is not None and curr != prev:
                await self._hooks.trigger("on_change", {
                    "cycle":      self._cycle,
                    "reading":    reading,
                    "prev_value": prev,
                    "delta":      round(curr - prev, 4),
                })

            # ── Hook: on_alarm — fires when threshold is crossed ──────────────
            if reading.in_alarm and not state.alarm_active:
                state.alarm_active = True
                await self._hooks.trigger("on_alarm", {
                    "cycle":   self._cycle,
                    "reading": reading,
                    "target":  state.target,
                })
            elif not reading.in_alarm:
                state.alarm_active = False

        if self._poll_cfg.log_to_csv:
            self._append_csv(readings)

    async def _read_one(self, state: PollState, ts: datetime) -> PollReading:
        """Read a single target and return a PollReading. Never raises."""
        t = state.target
        try:
            from bacpypes3.primitivedata import ObjectIdentifier
            obj_id = ObjectIdentifier(t.object_id)
            value  = await self._transport.read(self._target_addr, obj_id, "present-value")

            in_alarm = False
            try:
                fv = float(value)
                if t.low_alarm  is not None and fv < t.low_alarm:
                    in_alarm = True
                if t.high_alarm is not None and fv > t.high_alarm:
                    in_alarm = True
            except (TypeError, ValueError):
                pass

            return PollReading(
                timestamp = ts,
                object_id = t.object_id,
                label     = t.label,
                value     = value,
                unit      = t.unit,
                in_alarm  = in_alarm,
            )

        except Exception as err:
            log.warning(f"Poll read failed for {t.object_id}: {err}")
            return PollReading(
                timestamp = ts,
                object_id = t.object_id,
                label     = t.label,
                value     = None,
                unit      = t.unit,
                error     = str(err)[:60],
            )

    # =========================================================================
    # DISPLAY
    # =========================================================================

    def _build_table(self) -> Table:
        table = Table(
            title       = f"BACnet Live Monitor  |  Cycle {self._cycle}  |  {datetime.now().strftime('%H:%M:%S')}",
            title_style = "bold cyan",
            border_style= "cyan",
            expand      = True,
        )
        table.add_column("Object",   style="dim",        width=18)
        table.add_column("Label",    style="bold white", width=12)
        table.add_column("Value",    style="bold green", width=16, justify="right")
        table.add_column("Status",   width=12,           justify="center")
        table.add_column("Changed",  width=10,           justify="center")
        table.add_column("Reads",    width=8,            justify="right")
        table.add_column("Errors",   width=8,            justify="right")
        table.add_column("Last Read",width=12)

        for state in self._states.values():
            r = state.latest
            if r is None:
                table.add_row(state.target.object_id, state.target.label,
                              "—", "waiting...", "—", "0", "0", "—")
                continue

            if r.error:
                val_text = Text(r.value_str, style="bold red")
                status   = Text("⚠ ERROR",  style="bold red")
            elif r.in_alarm:
                val_text = Text(r.value_str, style="bold yellow")
                status   = Text("🚨 ALARM",  style="bold yellow")
            else:
                val_text = Text(r.value_str, style="bold green")
                status   = Text("✅ OK",     style="bold green")

            history = list(state.history)
            if len(history) >= 2:
                prev = history[-2]
                try:
                    delta = float(r.value) - float(prev.value)
                    if delta > 0:
                        changed = Text(f"↑ {delta:+.2f}", style="yellow")
                    elif delta < 0:
                        changed = Text(f"↓ {delta:+.2f}", style="cyan")
                    else:
                        changed = Text("—", style="dim")
                except (TypeError, ValueError):
                    changed = Text("—", style="dim")
            else:
                changed = Text("—", style="dim")

            table.add_row(
                r.object_id,
                r.label,
                val_text,
                status,
                changed,
                str(state.total_reads),
                str(state.error_count) if state.error_count > 0 else Text("0", style="dim"),
                r.timestamp.strftime("%H:%M:%S"),
            )

        table.add_section()
        table.add_row(
            f"[dim]Interval: {self._poll_cfg.interval}s[/dim]",
            "", "", "", "", "", "",
            "[dim]Ctrl+C to stop[/dim]",
        )
        return table

    def _print_plain_cycle(self) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        for state in self._states.values():
            r = state.latest
            if r:
                alarm_tag = " 🚨" if r.in_alarm else ""
                err_tag   = f" ⚠ {r.error}" if r.error else ""
                print(
                    f"[dim][{ts}][/dim] Cycle {self._cycle:04d} | "
                    f"[bold]{r.label}[/bold] ({r.object_id}) = "
                    f"[bold green]{r.value_str}[/bold green]{alarm_tag}{err_tag}"
                )

    def _print_summary(self) -> None:
        print(f"\n[bold cyan]{'─'*60}[/bold cyan]")
        print(f"[bold cyan] Polling Summary[/bold cyan]")
        print(f"[bold cyan]{'─'*60}[/bold cyan]")
        print(f" Total cycles : {self._cycle}")
        for state in self._states.values():
            print(
                f" {state.target.label:12s} : "
                f"{state.total_reads} reads | "
                f"{state.error_count} errors | "
                f"last = {state.latest.value_str if state.latest else '—'}"
            )
        print(f"[bold cyan]{'─'*60}[/bold cyan]\n")

    # =========================================================================
    # CSV LOGGING
    # =========================================================================

    def _append_csv(self, readings: list[PollReading]) -> None:
        is_new = not self._csv_path.exists()
        try:
            with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if is_new:
                    writer.writerow([
                        "timestamp", "cycle", "object_id", "label",
                        "value", "unit", "in_alarm", "error"
                    ])
                for r in readings:
                    writer.writerow([
                        r.timestamp.isoformat(), self._cycle,
                        r.object_id, r.label,
                        r.value if not r.error else "",
                        r.unit, r.in_alarm, r.error,
                    ])
        except Exception as csv_err:
            log.warning(f"CSV write failed: {csv_err}")