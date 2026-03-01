"""
================================================================================
 main.py  —  THE ENTRY POINT (Wiring Everything Together)
================================================================================

 ARCHITECTURE LESSON 7: Composition Root
 ─────────────────────────────────────────
 This file is called the "Composition Root" — the ONE place where all the
 pieces are assembled together. Think of it as the instruction manual for
 building the LEGO set.

 All the other files are individual LEGO bricks:
   config/settings.py  → cfg         (the blueprint)
   core/hooks.py       → HookManager (the event bus)
   core/transport.py   → BACnetTransport (the network layer)
   core/runner.py      → TestRunner  (the orchestrator)
   hooks/builtin.py    → plug-in hooks (optional extensions)

 THIS file:
   1. Creates each brick (cfg, hooks, transport)
   2. Plugs in the hooks you want
   3. Hands everything to TestRunner
   4. Runs it

 ARCHITECTURE LESSON 8: The Full Picture
 ─────────────────────────────────────────

 ┌─────────────────────────────────────────────────────────────────┐
 │                         main.py                                 │
 │  (Composition Root — assembles and wires all components)        │
 └──────┬──────────────────────────────────────────────────────────┘
        │ creates & injects
        ▼
 ┌──────────────┐    reads     ┌──────────────────┐
 │  TestRunner  │ ──────────── │  config/settings │
 │  (runner.py) │              │  AppConfig        │
 └──────┬───────┘              └──────────────────┘
        │
        │ delegates network calls
        ▼
 ┌──────────────────┐          ┌──────────────────┐
 │  BACnetTransport │          │  HookManager     │
 │  (transport.py)  │          │  (hooks.py)      │
 │                  │          │                  │
 │  .write()        │          │  "before_write"  │──► [your hook fns]
 │  .read()         │          │  "after_write"   │──► [your hook fns]
 └────────┬─────────┘          │  "on_fail"       │──► [your hook fns]
          │                    └──────────────────┘
          │ raw bacpypes3 calls
          ▼
 ┌──────────────────────────────┐
 │  bacpypes3 NormalApplication │
 │  UDP → 192.168.100.183:63205 │
 └──────────────────────────────┘

================================================================================
"""

import asyncio
import logging
import sys
from rich import print
from rich.traceback import install
from rich.logging import RichHandler

install(show_locals=False)
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)]
)

# ── Import all the bricks ─────────────────────────────────────────────────────
from config.settings import cfg, AppConfig, DUTConfig, TestConfig
from core.hooks import hooks
from core.transport import BACnetTransport
from core.runner import TestRunner
from hooks.builtin import register_development_hooks, register_production_hooks


# =============================================================================
# ⚙️  CUSTOMISE YOUR RUN HERE
# =============================================================================
# This is the only section you edit for day-to-day use.
# The rest of main.py is framework wiring — you don't touch it.

def configure() -> AppConfig:
    """
    Override any config values for this specific test run.

    ARCHITECTURE: This function is the "seam" between config and execution.
    You could swap this for reading from a YAML file, CLI args, or a database.
    """
    # ── Update the port Yabe shows for the simulator ──────────────────────────
    cfg.dut.port = 63205      # ⚠ update from Yabe after every restart

    # ── Change what value to inject ───────────────────────────────────────────
    cfg.test.test_value = 31.0

    # ── Change which object to target ─────────────────────────────────────────
    # cfg.dut.object_id = "analog-value,1"   # ← uncomment to target a different AV

    return cfg


def register_hooks() -> None:
    """
    Plug in the hooks you want for this run.

    ARCHITECTURE: This is your "hook wiring" section.
    Switch between development and production bundles,
    or mix-and-match individual hooks.

    Examples:
        register_development_hooks(hooks)   ← verbose, no files, for dev
        register_production_hooks(hooks)    ← audit CSV, safety guard, for prod

        # Or register individual hooks manually:
        from hooks.builtin import console_alert, csv_reporter
        hooks.register_fn("on_fail", console_alert)
        hooks.register_fn("on_pass", csv_reporter)

        # Or write your own inline hook:
        @hooks.register("on_pass")
        async def my_custom_hook(ctx):
            print(f"Custom hook fired! Result = {ctx['result']}")
    """
    # Switch to register_production_hooks(hooks) when running on live hardware
    register_development_hooks(hooks)


# =============================================================================
# 🚀  FRAMEWORK ENTRY POINT
# Do not edit below this line for normal use.
# =============================================================================

async def main() -> None:
    app_cfg = configure()
    register_hooks()

    print("[bold magenta]BACnet Testbench Framework — Starting...[/bold magenta]")
    print(f"[dim]DUT: {app_cfg.dut.ip}:{app_cfg.dut.port} | "
          f"Object: {app_cfg.dut.object_id} | "
          f"Inject: {app_cfg.test.test_value} °C[/dim]\n")

    # ── Use context manager to guarantee socket cleanup ───────────────────────
    # 'async with' calls transport.__aenter__() and __aexit__() automatically.
    # Even if TestRunner crashes, the socket is always closed.
    async with BACnetTransport(app_cfg.net) as transport:

        await asyncio.sleep(app_cfg.timing.socket_bind)

        runner = TestRunner(
            cfg=app_cfg,
            transport=transport,
            hooks=hooks,
        )

        result = await runner.run()

    # ── Final summary ─────────────────────────────────────────────────────────
    print(f"\n[dim]{'─'*60}[/dim]")
    print(f"[dim]Duration : {result.duration_ms}ms[/dim]")
    print(f"[dim]Steps    : {result.steps_done}[/dim]")
    print(f"[dim]Value    : {result.final_value} °C[/dim]")
    if result.error:
        print(f"[dim]Error    : {result.error}[/dim]")
    print(f"[dim]{'─'*60}[/dim]")

    # Exit code for CI/CD pipelines: 0 = pass, 1 = fail
    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
