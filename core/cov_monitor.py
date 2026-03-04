"""
================================================================================
 core/cov_monitor.py  —  THE COV (CHANGE OF VALUE) ENGINE
================================================================================

 ARCHITECTURE LESSON: How COV Differs from Polling
 ───────────────────────────────────────────────────

 POLLING (what main_poll.py does):
 ┌──────────┐   "What's T Indoor?"   ┌──────────┐
 │  Python  │ ─────────────────────► │   DUT    │
 │          │ ◄───────────────────── │          │
 │          │        "21.2°C"        │          │
 │          │                        │          │
 │  (wait   │                        │          │
 │   2 sec) │                        │          │
 │          │   "What's T Indoor?"   │          │
 │          │ ─────────────────────► │          │
 │          │ ◄───────────────────── │          │
 └──────────┘        "21.2°C"        └──────────┘
   Asks every 2s regardless of whether anything changed.

 COV (what this file does):
 ┌──────────┐  "Subscribe to T Indoor" ┌──────────┐
 │  Python  │ ──────────────────────►  │   DUT    │
 │          │ ◄──────────────────────  │          │
 │          │        "OK"              │          │
 │          │                          │          │
 │ (silent) │                          │(watching)│
 │          │                          │          │
 │          │  ◄─────────────────────  │          │
 │          │  "T Indoor changed: 25°C"│          │
 └──────────┘                          └──────────┘
   DUT only sends when value actually changes. Silent otherwise.

 HOW BACNET COV WORKS (3 steps):
 ─────────────────────────────────
 Step 1: SUBSCRIBE
   We send a SubscribeCOVRequest to the DUT.
   We say: "notify me when analog-input,0 changes, for 300 seconds."
   DUT replies: SimpleACK (confirmed) or nothing (unconfirmed).

 Step 2: RECEIVE NOTIFICATIONS
   Whenever T Indoor changes, DUT sends COVNotification to us.
   Notification contains: object, present-value, status-flags.
   We process it and fire hooks.

 Step 3: RESUBSCRIBE
   BACnet COV subscriptions expire after 'lifetime' seconds.
   We resubscribe at 80% of the lifetime to ensure continuity.
   A lifetime=0 subscription means "until I cancel" (use with care).

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

from bacpypes3.ipv4.app import NormalApplication
from bacpypes3.local.device import DeviceObject
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier, Unsigned
from bacpypes3.basetypes import PropertyIdentifier
from bacpypes3.apdu import (
    SubscribeCOVRequest,
    UnconfirmedCOVNotificationRequest,
    ConfirmedCOVNotificationRequest,
    SimpleAckPDU,
)

log = logging.getLogger("testbench.cov")
console = Console()


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class COVNotification:
    """
    One inbound notification received from the DUT.

    ARCHITECTURE LESSON: Immutable Event Record
    Every notification is captured as a timestamped record.
    We never overwrite — we append. This gives you a full audit trail
    of every value change that occurred during the session.
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
        if self.error:
            return f"ERROR: {self.error}"
        if self.value is None:
            return "—"
        if isinstance(self.value, bool):
            return "Active" if self.value else "Inactive"
        try:
            return f"{float(self.value):.2f} {self.unit}".strip()
        except (TypeError, ValueError):
            return str(self.value)


@dataclass
class COVState:
    """
    Tracks state for one subscribed object.
    Stores notification history and subscription health.
    """
    target:           object
    history:          deque  = field(default_factory=lambda: deque(maxlen=100))
    subscribed:       bool   = False
    sub_time:         datetime | None = None   # when we last subscribed
    notification_count: int  = 0
    alarm_active:     bool   = False

    def push(self, notif: COVNotification):
        self.history.append(notif)
        self.notification_count += 1

    @property
    def latest(self) -> COVNotification | None:
        return self.history[-1] if self.history else None

    @property
    def latest_value(self) -> float | None:
        n = self.latest
        if n and not n.error:
            try:
                return float(n.value)
            except (TypeError, ValueError):
                return None
        return None

    @property
    def sub_age_seconds(self) -> float | None:
        """How many seconds since we last subscribed."""
        if self.sub_time:
            return (datetime.now() - self.sub_time).total_seconds()
        return None


# =============================================================================
# COV APPLICATION
# =============================================================================

class COVApplication(NormalApplication):
    """
    ARCHITECTURE LESSON: Extending vs Wrapping
    ────────────────────────────────────────────
    For polling we WRAPPED NormalApplication inside BACnetTransport.
    For COV we must EXTEND NormalApplication because we need to override
    the incoming notification handler — a method that bacpypes3 calls
    when a packet arrives.

    Wrapping = "I hold a reference to you and call your methods"
    Extending = "I AM you, but I override some of your behaviour"

    COV requires extending because bacpypes3 calls do_*Request methods
    on the app object itself when packets arrive. We can't intercept that
    from a wrapper class.

    This is called the "Template Method Pattern":
      bacpypes3 defines WHEN to call do_UnconfirmedCOVNotificationRequest
      We define WHAT to do when it's called.
    """

    def __init__(self, device: DeviceObject, local_address: Address):
        super().__init__(device, local_address)
        # This queue is how notifications flow from the network handler
        # (which runs in bacpypes3's async internals) to our COVMonitor.
        # asyncio.Queue is thread-safe and async-compatible.
        self.notification_queue: asyncio.Queue = asyncio.Queue()

    async def do_UnconfirmedCOVNotificationRequest(self, apdu) -> None:
        """
        Called automatically by bacpypes3 when an UNCONFIRMED COV
        notification packet arrives from the DUT.

        We extract the value and put it on the queue.
        COVMonitor._notification_worker() picks it up and processes it.

        ARCHITECTURE: We keep this method THIN.
        It only extracts data and enqueues it.
        All business logic (hooks, alarms, display) is in COVMonitor.
        """
        await self._handle_cov_notification(apdu, confirmed=False)

    async def do_ConfirmedCOVNotificationRequest(self, apdu) -> None:
        """
        Called automatically by bacpypes3 when a CONFIRMED COV
        notification packet arrives. We must send a SimpleACK reply.
        """
        # Send ACK back to DUT — required for confirmed notifications
        await self.response(SimpleAckPDU(context=apdu))
        await self._handle_cov_notification(apdu, confirmed=True)

    async def _handle_cov_notification(self, apdu, confirmed: bool) -> None:
        """Extract property values from the COV notification APDU and enqueue."""
        try:
            obj_id = str(apdu.monitoredObjectIdentifier)
            values = {}

            # COV notifications carry a list of property values
            # We extract present-value and status-flags
            for element in apdu.listOfValues:
                prop_name = str(element.propertyIdentifier)
                values[prop_name] = element.value

            present_value = values.get("present-value")

            await self.notification_queue.put({
                "object_id":    obj_id,
                "present_value": present_value,
                "confirmed":    confirmed,
                "timestamp":    datetime.now(),
            })

        except Exception as err:
            log.warning(f"COV notification parse error: {err}")


# =============================================================================
# THE COV MONITOR
# =============================================================================

class COVMonitor:
    """
    Manages COV subscriptions and processes incoming notifications.

    Lifecycle:
      1. connect()      — create COVApplication, bind UDP
      2. subscribe_all() — send SubscribeCOVRequest for each target
      3. run()          — start notification worker + resubscribe loop
      4. Ctrl+C         — graceful unsubscribe + disconnect

    Usage:
        monitor = COVMonitor(cfg, hooks)
        await monitor.run()
    """

    def __init__(self, cfg, hooks):
        self._cfg      = cfg
        self._hooks    = hooks
        self._cov_cfg  = cfg.cov

        self._app: COVApplication | None = None
        self._target_addr = Address(f"{cfg.dut.ip}:{cfg.dut.port}")

        # Build one COVState per target
        self._states: dict[str, COVState] = {
            t.object_id: COVState(target=t)
            for t in self._cov_cfg.cov_targets
        }

        self._running    = False
        self._csv_path   = Path("reports/cov_log.csv")
        self._total_notifs = 0

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    async def run(self) -> None:
        """Connect, subscribe, monitor. Handles Ctrl+C gracefully."""
        await self._connect()

        print(f"\n[bold cyan]{'─'*60}[/bold cyan]")
        print(f"[bold cyan] BACnet COV Monitor Starting[/bold cyan]")
        print(f"[bold cyan] DUT         : {self._target_addr}[/bold cyan]")
        print(f"[bold cyan] Targets     : {len(self._states)} objects[/bold cyan]")
        print(f"[bold cyan] Lifetime    : {self._cov_cfg.lifetime}s (resubscribe at "
              f"{int(self._cov_cfg.lifetime * self._cov_cfg.resubscribe_margin)}s)[/bold cyan]")
        print(f"[bold cyan] Mode        : Event-driven push (zero polling)[/bold cyan]")
        print(f"[bold cyan]{'─'*60}[/bold cyan]")
        print("[dim]Press Ctrl+C to unsubscribe and exit.[/dim]\n")

        if self._cov_cfg.log_to_csv:
            self._csv_path.parent.mkdir(parents=True, exist_ok=True)

        await self._subscribe_all()

        self._running = True
        try:
            if self._cov_cfg.show_live_table:
                await self._run_with_live_table()
            else:
                await self._run_plain()

        except KeyboardInterrupt:
            print("\n[yellow]COV monitor stopped by user (Ctrl+C)[/yellow]")
        finally:
            self._running = False
            await self._unsubscribe_all()
            await self._disconnect()
            self._print_summary()

    # =========================================================================
    # CONNECTION
    # =========================================================================

    async def _connect(self) -> None:
        """Instantiate COVApplication and bind UDP socket."""
        device = DeviceObject(
            objectIdentifier=("device", self._cfg.net.device_id),
            objectName=self._cfg.net.device_name,
            vendorIdentifier=self._cfg.net.vendor_id,
        )
        local_addr = Address(f"{self._cfg.net.local_ip}:{self._cfg.net.local_port}")
        self._app  = COVApplication(device, local_addr)
        await asyncio.sleep(self._cfg.timing.socket_bind)
        log.info(f"COV app bound to {self._cfg.net.local_ip}:{self._cfg.net.local_port}")

    async def _disconnect(self) -> None:
        if self._app:
            self._app.close()
            self._app = None
            log.info("COV app disconnected")

    # =========================================================================
    # SUBSCRIPTION MANAGEMENT
    # =========================================================================

    async def _subscribe_all(self) -> None:
        """Send SubscribeCOVRequest for every target concurrently."""
        print("[dim]Subscribing to all targets...[/dim]")
        tasks = [self._subscribe_one(state) for state in self._states.values()]
        await asyncio.gather(*tasks)
        subscribed = sum(1 for s in self._states.values() if s.subscribed)
        print(f"[green]  ✅ {subscribed}/{len(self._states)} subscriptions active[/green]\n")

    async def _subscribe_one(self, state: COVState) -> None:
        """
        Send a SubscribeCOVRequest for one object.

        BACNET COV SUBSCRIPTION ANATOMY:
          subscriberProcessIdentifier: our local ID for this subscription
          monitoredObjectIdentifier:   which object to watch
          issueConfirmedNotifications: True = ACK required, False = fire-and-forget
          lifetime:                    how long (seconds) before auto-expiry
                                       0 = permanent (cancel by resubscribing
                                           with cancellationRequest=True)
        """
        t = state.target
        try:
            request = SubscribeCOVRequest(
                subscriberProcessIdentifier = self._cov_cfg.process_id,
                monitoredObjectIdentifier   = ObjectIdentifier(t.object_id),
                issueConfirmedNotifications = t.confirmed,
                lifetime                    = Unsigned(self._cov_cfg.lifetime),
            )
            request.pduDestination = self._target_addr

            await self._app.request(request)

            state.subscribed = True
            state.sub_time   = datetime.now()
            log.info(f"Subscribed: {t.label} ({t.object_id}) | "
                     f"confirmed={t.confirmed} | lifetime={self._cov_cfg.lifetime}s")

        except Exception as err:
            log.error(f"Subscribe failed for {t.object_id}: {err}")
            state.subscribed = False

    async def _unsubscribe_all(self) -> None:
        """Cancel all COV subscriptions gracefully before exit."""
        print("[dim]Cancelling COV subscriptions...[/dim]")
        tasks = [self._unsubscribe_one(state) for state in self._states.values()]
        await asyncio.gather(*tasks)
        print("[dim]All subscriptions cancelled.[/dim]")

    async def _unsubscribe_one(self, state: COVState) -> None:
        """Cancel a single COV subscription (lifetime=0 signals cancellation)."""
        if not state.subscribed:
            return
        try:
            request = SubscribeCOVRequest(
                subscriberProcessIdentifier = self._cov_cfg.process_id,
                monitoredObjectIdentifier   = ObjectIdentifier(state.target.object_id),
                # Omitting issueConfirmedNotifications and lifetime = cancellation
            )
            request.pduDestination = self._target_addr
            await self._app.request(request)
            state.subscribed = False
        except Exception as err:
            log.warning(f"Unsubscribe failed for {state.target.object_id}: {err}")

    async def _resubscribe_loop(self) -> None:
        """
        Background task: resubscribes before the lifetime expires.

        ARCHITECTURE LESSON: Background Task with asyncio.create_task()
        ──────────────────────────────────────────────────────────────
        asyncio.create_task() runs a coroutine concurrently without
        blocking the main loop. The notification worker and resubscribe
        loop run at the same time — neither blocks the other.

        This is the async equivalent of running two threads, but without
        the complexity of locks and race conditions.
        """
        resubscribe_after = self._cov_cfg.lifetime * self._cov_cfg.resubscribe_margin
        while self._running:
            await asyncio.sleep(resubscribe_after)
            if not self._running:
                break
            log.info("Resubscribing all COV targets...")
            await self._subscribe_all()

    # =========================================================================
    # NOTIFICATION PROCESSING
    # =========================================================================

    async def _notification_worker(self) -> None:
        """
        ARCHITECTURE LESSON: Producer-Consumer with asyncio.Queue
        ─────────────────────────────────────────────────────────
        COVApplication (producer) puts notifications on the queue.
        This worker (consumer) takes them off and processes them.

        Why a queue instead of calling process directly?
          - COVApplication runs inside bacpypes3's internals
          - We don't want heavy processing (CSV, hooks, display) blocking
            the network handler
          - The queue decouples "receiving" from "processing"
          - If 10 notifications arrive at once, they queue up safely

        This pattern is called Producer-Consumer and is fundamental
        to event-driven systems.
        """
        while self._running:
            try:
                # Wait up to 0.5s for a notification, then loop to check _running
                raw = await asyncio.wait_for(
                    self._app.notification_queue.get(),
                    timeout=0.5
                )
                await self._process_notification(raw)
            except asyncio.TimeoutError:
                continue   # no notification arrived — loop and check _running
            except Exception as err:
                log.warning(f"Notification worker error: {err}")

    async def _process_notification(self, raw: dict) -> None:
        """Process one raw notification dict into a COVNotification."""
        obj_id    = raw["object_id"]
        raw_value = raw["present_value"]
        ts        = raw["timestamp"]

        # Find matching state — obj_id format from apdu may differ slightly
        # Try exact match first, then partial match
        state = self._states.get(obj_id)
        if state is None:
            # bacpypes3 may format as "analog-input:0" — normalise
            normalised = obj_id.replace(":", ",")
            state = self._states.get(normalised)
        if state is None:
            log.debug(f"Received COV for untracked object: {obj_id}")
            return

        t = state.target
        prev_value = state.latest_value

        # Decode value
        try:
            value = float(raw_value) if raw_value is not None else None
        except (TypeError, ValueError):
            value = str(raw_value) if raw_value is not None else None

        # Check alarm thresholds
        in_alarm = False
        if value is not None:
            try:
                fv = float(value)
                if t.low_alarm  is not None and fv < t.low_alarm:
                    in_alarm = True
                if t.high_alarm is not None and fv > t.high_alarm:
                    in_alarm = True
            except (TypeError, ValueError):
                pass

        notif = COVNotification(
            timestamp = ts,
            object_id = t.object_id,
            label     = t.label,
            value     = value,
            unit      = t.unit,
            in_alarm  = in_alarm,
        )

        state.push(notif)
        self._total_notifs += 1

        # ── Hook: on_cov — every notification ────────────────────────────
        await self._hooks.trigger("on_cov", {
            "notification": notif,
            "state":        state,
        })

        # ── Hook: on_cov_change — value differs from previous ─────────────
        curr = state.latest_value
        if prev_value is not None and curr is not None and curr != prev_value:
            delta = round(curr - prev_value, 4)
            await self._hooks.trigger("on_cov_change", {
                "notification": notif,
                "prev_value":   prev_value,
                "delta":        delta,
            })

        # ── Hook: on_cov_alarm — threshold crossed ─────────────────────────
        if in_alarm and not state.alarm_active:
            state.alarm_active = True
            await self._hooks.trigger("on_cov_alarm", {
                "notification": notif,
                "target":       t,
            })
        elif not in_alarm:
            state.alarm_active = False

        # Log to CSV
        if self._cov_cfg.log_to_csv:
            self._append_csv(notif)

    # =========================================================================
    # MAIN LOOPS
    # =========================================================================

    async def _run_with_live_table(self) -> None:
        """
        Run notification worker + resubscribe loop + live table concurrently.

        ARCHITECTURE LESSON: asyncio.gather() for concurrent tasks
        Three coroutines run simultaneously:
          1. _notification_worker — processes incoming COV packets
          2. _resubscribe_loop   — renews subscriptions before expiry
          3. _live_table_loop    — refreshes the display every second

        None of these block each other. This is cooperative multitasking.
        """
        async def live_table_loop(live):
            while self._running:
                live.update(self._build_table())
                await asyncio.sleep(1.0)

        with Live(self._build_table(), refresh_per_second=2, console=console) as live:
            await asyncio.gather(
                self._notification_worker(),
                self._resubscribe_loop(),
                live_table_loop(live),
            )

    async def _run_plain(self) -> None:
        """Run without live table — notifications print as they arrive."""
        await asyncio.gather(
            self._notification_worker(),
            self._resubscribe_loop(),
        )

    # =========================================================================
    # DISPLAY
    # =========================================================================

    def _build_table(self) -> Table:
        table = Table(
            title        = f"BACnet COV Monitor  |  {self._total_notifs} notifications  |  {datetime.now().strftime('%H:%M:%S')}",
            title_style  = "bold magenta",
            border_style = "magenta",
            expand       = True,
        )
        table.add_column("Object",         style="dim",          width=20)
        table.add_column("Label",          style="bold white",   width=12)
        table.add_column("Value",          width=16,             justify="right")
        table.add_column("Status",         width=12,             justify="center")
        table.add_column("Notifications",  width=14,             justify="right")
        table.add_column("Sub",            width=6,              justify="center")
        table.add_column("Last Change",    width=12)

        for state in self._states.values():
            n = state.latest

            sub_icon = Text("✅", style="green") if state.subscribed else Text("❌", style="red")

            if n is None:
                table.add_row(
                    state.target.object_id, state.target.label,
                    "waiting...", "—",
                    "0", sub_icon, "—"
                )
                continue

            if n.error:
                val_text = Text(n.value_str, style="bold red")
                status   = Text("⚠ ERROR",   style="bold red")
            elif n.in_alarm:
                val_text = Text(n.value_str, style="bold yellow")
                status   = Text("🚨 ALARM",   style="bold yellow")
            else:
                val_text = Text(n.value_str, style="bold green")
                status   = Text("✅ OK",      style="bold green")

            table.add_row(
                n.object_id,
                n.label,
                val_text,
                status,
                str(state.notification_count),
                sub_icon,
                n.timestamp.strftime("%H:%M:%S"),
            )

        table.add_section()
        table.add_row(
            "[dim]Event-driven — zero polling[/dim]",
            "", "", "", "", "",
            "[dim]Ctrl+C to exit[/dim]",
        )
        return table

    def _print_summary(self) -> None:
        print(f"\n[bold magenta]{'─'*60}[/bold magenta]")
        print(f"[bold magenta] COV Session Summary[/bold magenta]")
        print(f"[bold magenta]{'─'*60}[/bold magenta]")
        print(f" Total notifications : {self._total_notifs}")
        for state in self._states.values():
            n = state.latest
            print(
                f" {state.target.label:12s} : "
                f"{state.notification_count:4d} notifications | "
                f"last = {n.value_str if n else '—'}"
            )
        print(f"[bold magenta]{'─'*60}[/bold magenta]\n")

    # =========================================================================
    # CSV LOGGING
    # =========================================================================

    def _append_csv(self, notif: COVNotification) -> None:
        is_new = not self._csv_path.exists()
        try:
            with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if is_new:
                    writer.writerow([
                        "timestamp", "object_id", "label",
                        "value", "unit", "in_alarm"
                    ])
                writer.writerow([
                    notif.timestamp.isoformat(),
                    notif.object_id, notif.label,
                    notif.value, notif.unit, notif.in_alarm,
                ])
        except Exception as csv_err:
            log.warning(f"CSV write failed: {csv_err}")
