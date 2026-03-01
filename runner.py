"""
================================================================================
 core/runner.py  —  THE TEST ORCHESTRATOR
================================================================================

 ARCHITECTURE LESSON 4: Orchestrator Pattern
 ─────────────────────────────────────────────
 The Orchestrator knows the ORDER of steps but doesn't do the actual work.
 It delegates each step to the right specialist.

 Analogy — Orchestra Conductor:
   The conductor doesn't play any instrument.
   They wave a baton to tell each section WHEN to play.
   The violins (Transport) do the actual music.
   The conductor coordinates timing and order.

 TestRunner is the conductor:
   It calls transport.write()  → Transport handles the network
   It calls hooks.trigger()    → HookManager notifies all listeners
   It reads from cfg           → Config provides all values
   It doesn't directly talk to bacpypes3 at all

 ARCHITECTURE LESSON 5: Dependency Injection (DI)
 ──────────────────────────────────────────────────
 TestRunner does NOT create its own transport or hooks.
 It RECEIVES them from outside (injected via __init__).
 This is called Dependency Injection.

 Without DI (tightly coupled — bad):
   class TestRunner:
       def __init__(self):
           self.transport = BACnetTransport()   # ← hardcoded dependency
           self.hooks = HookManager()           # ← can't swap for testing

 With DI (loosely coupled — good):
   class TestRunner:
       def __init__(self, transport, hooks):   # ← injected from outside
           self.transport = transport
           self.hooks = hooks

 Benefits of DI:
   - In unit tests, inject a FakeTransport that doesn't need real hardware
   - Swap hooks for different environments (dev vs production)
   - Each class is independently testable

================================================================================
"""

import asyncio
import logging
from datetime import datetime

from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier

from config.settings import AppConfig
from core.transport import BACnetTransport
from core.hooks import HookManager

log = logging.getLogger("testbench.runner")


class TestResult:
    """
    ARCHITECTURE LESSON: Value Object
    ────────────────────────────────────
    Instead of returning raw True/False, return an object that carries
    all the context about what happened. This is called a "Value Object".
    It makes your code self-documenting and easier to log/serialize.
    """
    def __init__(self):
        self.passed      = False
        self.steps_done  = []       # list of completed step names
        self.final_value = None     # what was read back
        self.error       = None     # exception if failed
        self.duration_ms = 0        # how long the test took

    def __repr__(self):
        status = "PASS ✅" if self.passed else "FAIL ❌"
        return (
            f"TestResult({status} | "
            f"steps={self.steps_done} | "
            f"value={self.final_value} | "
            f"duration={self.duration_ms}ms)"
        )


class TestRunner:
    """
    Orchestrates the 4-step BACnet override test sequence.
    Delegates network calls to BACnetTransport.
    Fires hooks at key moments so external code can react.

    ARCHITECTURE: This class is the "business logic" layer.
    It knows WHAT to do but not HOW the network works (that's Transport's job).
    """

    def __init__(
        self,
        cfg:       AppConfig,
        transport: BACnetTransport,
        hooks:     HookManager,
    ):
        # ── Dependency Injection ──────────────────────────────────────────────
        # We store references, not create new objects.
        # This means the same transport/hooks can be shared across multiple runners.
        self._cfg       = cfg
        self._transport = transport
        self._hooks     = hooks

        # Pre-build Address and ObjectIdentifier once — reuse every step
        self._target = BACnetTransport.make_address(
            cfg.dut.ip, cfg.dut.port
        )
        self._obj_id = BACnetTransport.make_object_id(
            *cfg.dut.object_id.split(",")   # "analog-value,0" → ("analog-value", "0")
        )

    # =========================================================================
    # PUBLIC API — what callers use
    # =========================================================================

    async def run(self) -> TestResult:
        """
        Execute the full test sequence.
        Always restores Out-Of-Service in finally, even on crash.
        Returns a TestResult describing what happened.
        """
        result     = TestResult()
        start_time = datetime.now()
        oos_active = False   # track whether we need to restore

        self._header()

        try:
            # ── Pre-flight read ───────────────────────────────────────────────
            await self._pre_flight_check()

            # ── Step 1: Assert Out-Of-Service ─────────────────────────────────
            await self._step_assert_oos(result)
            oos_active = True

            # ── Step 2: Verify Out-Of-Service landed ──────────────────────────
            await self._step_verify_oos(result)

            # ── Step 3: Inject test value ─────────────────────────────────────
            await self._step_inject(result)

            # ── Step 4: Read-back verification ───────────────────────────────
            await self._step_verify_value(result)

            # ── All steps passed ──────────────────────────────────────────────
            result.passed = True
            await self._hooks.trigger("on_pass", {
                "result": result,
                "target": str(self._target),
                "object": self._cfg.dut.object_id,
            })
            print(f"\n[bold black on green] ✅ PASS — DUT responded correctly [/bold black on green]")

        except Exception as err:
            result.error = err
            log.error(f"Test failed: {err}")
            await self._hooks.trigger("on_fail", {
                "result": result,
                "error":  str(err),
                "target": str(self._target),
            })
            print(f"\n[bold white on red] FAIL [/bold white on red] {err}")

        finally:
            # ── ALWAYS restore Out-Of-Service ─────────────────────────────────
            # This block runs whether the test passed, failed, or crashed.
            if oos_active:
                await self._restore_oos(result)

            result.duration_ms = int(
                (datetime.now() - start_time).total_seconds() * 1000
            )
            log.info(f"Test complete: {result}")

        return result

    # =========================================================================
    # PRIVATE STEPS — internal implementation details
    # =========================================================================
    # Convention: methods starting with _ are "private" (internal only).
    # They're not meant to be called from outside this class.
    # This keeps the public API clean and the internals hidden.

    def _header(self):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[bold cyan]{'─'*60}[/bold cyan]")
        print(f"[bold cyan] BACnet Testbench — {ts}[/bold cyan]")
        print(f"[bold cyan] DUT    : {self._target}[/bold cyan]")
        print(f"[bold cyan] Object : {self._cfg.dut.object_id}[/bold cyan]")
        print(f"[bold cyan] Inject : {self._cfg.test.test_value} °C @ P{self._cfg.test.write_priority}[/bold cyan]")
        print(f"[bold cyan]{'─'*60}[/bold cyan]\n")

    async def _pre_flight_check(self):
        """Read baseline state before touching anything."""
        log.info("Pre-flight | reading baseline out-of-service state")
        baseline_oos = await self._transport.read(
            self._target, self._obj_id, "out-of-service"
        )
        log.info(f"Pre-flight | baseline out-of-service = {baseline_oos}")
        if baseline_oos:
            log.warning(
                "Pre-flight | out-of-service is already True before test started. "
                "A previous run may not have restored correctly. Proceeding anyway."
            )

    async def _step_assert_oos(self, result: TestResult):
        """Step 1 — Set out-of-service = True to decouple hardware."""
        log.info("Step 1 | WRITE out-of-service → True")

        await self._hooks.trigger("before_write", {
            "step": 1, "property": "out-of-service", "value": True
        })

        await self._transport.write(
            self._target, self._obj_id,
            "out-of-service", True
        )
        await asyncio.sleep(self._cfg.timing.post_write)

        await self._hooks.trigger("after_write", {
            "step": 1, "property": "out-of-service", "value": True
        })

        result.steps_done.append("assert_oos")
        print("[green]  ✅ Step 1 — hardware decoupled[/green]")

    async def _step_verify_oos(self, result: TestResult):
        """Step 2 — Read back to confirm out-of-service actually landed."""
        log.info("Step 2 | READ out-of-service (verify Step 1)")

        await self._hooks.trigger("before_read", {
            "step": 2, "property": "out-of-service"
        })

        oos_val = await self._transport.read(
            self._target, self._obj_id, "out-of-service"
        )
        await asyncio.sleep(self._cfg.timing.post_write)

        await self._hooks.trigger("after_read", {
            "step": 2, "property": "out-of-service", "value": oos_val
        })

        if not oos_val:
            raise RuntimeError(
                "Step 2 FAILED: out-of-service did not assert True. "
                "Write 1 may have been rejected — check priority array or object permissions."
            )

        result.steps_done.append("verify_oos")
        print(f"[green]  ✅ Step 2 — out-of-service confirmed = {oos_val}[/green]")

    async def _step_inject(self, result: TestResult):
        """Step 3 — Inject the test value at the configured priority."""
        val = self._cfg.test.test_value
        pri = self._cfg.test.write_priority
        log.info(f"Step 3 | WRITE present-value → {val} @ priority {pri}")

        await self._hooks.trigger("before_write", {
            "step": 3, "property": "present-value",
            "value": val, "priority": pri
        })

        await self._transport.write(
            self._target, self._obj_id,
            "present-value", val,
            priority=pri,
        )
        await asyncio.sleep(self._cfg.timing.verify_read)

        await self._hooks.trigger("after_write", {
            "step": 3, "property": "present-value", "value": val
        })

        result.steps_done.append("inject_value")
        print(f"[green]  ✅ Step 3 — {val} °C injected @ priority {pri}[/green]")

    async def _step_verify_value(self, result: TestResult):
        """Step 4 — Read back present-value and assert it matches expected."""
        log.info("Step 4 | READ present-value (verify Step 3)")

        await self._hooks.trigger("before_read", {
            "step": 4, "property": "present-value"
        })

        actual = await self._transport.read(
            self._target, self._obj_id, "present-value"
        )
        result.final_value = actual

        await self._hooks.trigger("after_read", {
            "step": 4, "property": "present-value", "value": actual
        })

        expected  = self._cfg.test.test_value
        tolerance = self._cfg.test.tolerance
        delta     = abs(float(actual) - expected)

        print(f"[blue]  Read-back: [bold green]{actual} °C[/bold green][/blue]")

        if delta > tolerance:
            raise AssertionError(
                f"Step 4 FAILED: expected {expected} °C, got {actual} °C. "
                f"Delta = {delta:.4f} (tolerance = {tolerance}). "
                f"Check if a higher-priority source is overriding P{self._cfg.test.write_priority}."
            )

        result.steps_done.append("verify_value")
        print(f"[green]  ✅ Step 4 — value verified ({actual} °C)[/green]")

    async def _restore_oos(self, result: TestResult):
        """
        Safety restore — ALWAYS runs in finally block.
        Logs CRITICAL if it fails so a human knows to check manually.
        """
        log.info("Restore | out-of-service → False")
        try:
            await self._transport.write(
                self._target, self._obj_id,
                "out-of-service", False
            )
            await self._hooks.trigger("on_restore", {
                "result": result, "success": True
            })
            print("[dim]  Out-Of-Service restored → False ✅[/dim]")
        except Exception as restore_err:
            log.critical(
                f"RESTORE FAILED — Out-Of-Service may still be True on {self._target}!\n"
                f"Error: {restore_err}\n"
                f"ACTION REQUIRED: Manually verify controller state in Yabe."
            )
            await self._hooks.trigger("on_restore", {
                "result": result, "success": False, "error": str(restore_err)
            })
