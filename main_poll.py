"""
================================================================================
 main_poll.py  —  ENTRY POINT FOR CONTINUOUS POLLING MODE
================================================================================
 HOW TO RUN:
   python main_poll.py                  ← poll forever, live table
   python main_poll.py --plain          ← poll forever, plain lines
   python main_poll.py --cycles 10      ← poll 10 times then stop
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
from core.transport import BACnetTransport
from core.poller import Poller
from hooks.poll_hooks import register_poll_hooks


def configure():
    cfg.dut.port             = 62532   # ⚠ update from Yabe after every restart
    cfg.poll.interval        = 2.0
    cfg.poll.max_cycles      = 0       # 0 = forever
    cfg.poll.log_to_csv      = True
    cfg.poll.show_live_table = True
    return cfg


def register_hooks():
    register_poll_hooks(hooks)

    # Add your own hooks here:
    # @hooks.register("on_poll")
    # async def my_hook(ctx):
    #     print(f"Cycle {ctx['cycle']} | {ctx['reading'].value_str}")


async def main():
    app_cfg = configure()
    register_hooks()

    if "--plain" in sys.argv:
        app_cfg.poll.show_live_table = False

    if "--cycles" in sys.argv:
        idx = sys.argv.index("--cycles")
        try:
            app_cfg.poll.max_cycles = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            print("[red]--cycles requires an integer argument[/red]")
            sys.exit(1)

    print("[bold magenta]BACnet Continuous Poller — Starting...[/bold magenta]")
    print(
        f"[dim]DUT: {app_cfg.dut.ip}:{app_cfg.dut.port} | "
        f"Interval: {app_cfg.poll.interval}s | "
        f"Targets: {len(app_cfg.poll.poll_targets)}[/dim]"
    )

    async with BACnetTransport(app_cfg.net) as transport:
        await asyncio.sleep(app_cfg.timing.socket_bind)
        poller = Poller(cfg=app_cfg, transport=transport, hooks=hooks)
        await poller.run()


if __name__ == "__main__":
    asyncio.run(main())