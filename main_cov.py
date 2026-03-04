"""
================================================================================
 main_cov.py  —  ENTRY POINT FOR COV EVENT-DRIVEN MONITORING
================================================================================
 HOW TO RUN:
   python main_cov.py              ← live table, event-driven
   python main_cov.py --plain      ← plain line output

 You now have THREE modes from ONE framework:
   python main.py        → one-shot inject & verify test
   python main_poll.py   → continuous polling (pull-based)
   python main_cov.py    → continuous COV monitoring (push-based)
================================================================================
"""

import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    import asyncio.base_events
    asyncio.base_events._set_reuseport = lambda sock: None
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from rich import print
from rich.logging import RichHandler
from rich.traceback import install

install(show_locals=False)
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)]
)

from config.settings import cfg
from core.hooks import hooks
from core.cov_monitor import COVMonitor
from hooks.cov_hooks import register_cov_hooks


def configure():
    cfg.dut.port                = 53218   # ⚠ update from Yabe after every restart
    cfg.cov.lifetime            = 300     # subscription lifetime in seconds
    cfg.cov.show_live_table     = True
    cfg.cov.log_to_csv          = True
    return cfg


def register_hooks():
    register_cov_hooks(hooks)

    # Add your own COV hooks:
    # @hooks.register("on_cov")
    # async def my_hook(ctx):
    #     print(f"Notification: {ctx['notification'].value_str}")


async def main():
    app_cfg = configure()
    register_hooks()

    if "--plain" in sys.argv:
        app_cfg.cov.show_live_table = False

    print("[bold magenta]BACnet COV Monitor — Starting...[/bold magenta]")
    print(
        f"[dim]DUT: {app_cfg.dut.ip}:{app_cfg.dut.port} | "
        f"Targets: {len(app_cfg.cov.cov_targets)} | "
        f"Mode: event-driven push[/dim]\n"
    )

    monitor = COVMonitor(cfg=app_cfg, hooks=hooks)
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
