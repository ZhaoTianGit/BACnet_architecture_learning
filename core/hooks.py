"""
================================================================================
 core/hooks.py  —  THE HOOK SYSTEM
================================================================================

 ARCHITECTURE LESSON 2: What Is a Hook?
 ────────────────────────────────────────
 A "hook" is a slot in your code where you can PLUG IN custom behaviour
 without touching the core logic.

 Real-world analogy — Power Strip:
   The power strip (your framework) has fixed slots.
   You plug in whatever appliance (hook function) you want.
   The strip doesn't know or care what's plugged in.
   You can swap appliances without rewiring the house.

 Code analogy — Git Hooks:
   Git has "pre-commit" and "post-commit" hooks.
   You plug in your own script (linter, tests, etc).
   Git runs your script at the right moment automatically.
   You didn't change Git's source code — you just plugged into its hook.

 In THIS framework:
   ┌────────────────────────────────────────────┐
   │  HookManager                               │
   │                                            │
   │  "before_write"  ──► [your functions here] │
   │  "after_write"   ──► [your functions here] │
   │  "before_read"   ──► [your functions here] │
   │  "after_read"    ──► [your functions here] │
   │  "on_pass"       ──► [your functions here] │
   │  "on_fail"       ──► [your functions here] │
   └────────────────────────────────────────────┘

 Example: you want to send a Slack alert when a test fails.
   ❌ Bad: edit core test logic and add Slack code inside it
   ✅ Good: write a Slack function, plug it into the "on_fail" hook
            The core logic never changes. You just extended it.

 This pattern is also called:
   - Event System / Event Bus
   - Observer Pattern
   - Middleware / Pipeline
   - Signal/Slot (Qt framework)

================================================================================
"""

import asyncio
import logging
from typing import Callable, Any

log = logging.getLogger("testbench.hooks")


class HookManager:
    """
    Manages named hook slots and runs all registered functions when triggered.

    Usage:
        hooks = HookManager()

        # Register a function into a hook slot
        @hooks.register("on_fail")
        async def my_alert(ctx):
            print(f"ALERT: test failed! Context = {ctx}")

        # Later, trigger the hook (framework does this automatically)
        await hooks.trigger("on_fail", {"step": 3, "error": "timeout"})
        # → my_alert() gets called automatically
    """

    # ── ARCHITECTURE: Class variable vs Instance variable ─────────────────────
    # _slots defines the VALID hook names (a whitelist).
    # This is a class variable — shared by all instances.
    # This prevents typos like "on_faill" silently doing nothing.
    _slots = {
        "before_write",   # fires just before any write_property call
        "after_write",    # fires just after a successful write
        "before_read",    # fires just before any read_property call
        "after_read",     # fires just after a successful read
        "on_pass",        # fires when the entire test sequence passes
        "on_fail",        # fires when any step raises an exception
        "on_restore",     # fires after Out-Of-Service is restored
        # ── NEW: polling slots ──────────────────
        "on_poll",      # fires every read cycle
        "on_change",    # fires when value changes
        "on_alarm",     # fires when threshold crossed
    }

    def __init__(self):
        # _registry is a dict of lists:
        # { "on_fail": [fn1, fn2, fn3], "on_pass": [fn4], ... }
        self._registry: dict[str, list[Callable]] = {slot: [] for slot in self._slots}

    # ── ARCHITECTURE: Decorator Pattern ──────────────────────────────────────
    # A decorator is a function that wraps another function.
    # The @ symbol is Python's decorator syntax.
    #
    # Without decorator (verbose):
    #   async def my_fn(ctx): ...
    #   hooks.register_fn("on_fail", my_fn)
    #
    # With decorator (clean):
    #   @hooks.register("on_fail")
    #   async def my_fn(ctx): ...
    #
    # Both do exactly the same thing. The decorator is just cleaner syntax.

    def register(self, slot: str) -> Callable:
        """
        Decorator: plug a function into a named hook slot.

        Example:
            @hooks.register("on_fail")
            async def alert(ctx):
                print("Test failed!", ctx)
        """
        if slot not in self._slots:
            raise ValueError(
                f"Unknown hook slot '{slot}'. "
                f"Valid slots: {sorted(self._slots)}"
            )

        def decorator(fn: Callable) -> Callable:
            self._registry[slot].append(fn)
            log.debug(f"Hook registered: '{slot}' ← {fn.__name__}()")
            return fn   # return fn unchanged so it still works normally

        return decorator

    def register_fn(self, slot: str, fn: Callable) -> None:
        """
        Non-decorator version of register. Useful for programmatic registration.

        Example:
            hooks.register_fn("on_fail", my_alert_function)
        """
        if slot not in self._slots:
            raise ValueError(f"Unknown hook slot '{slot}'.")
        self._registry[slot].append(fn)

    async def trigger(self, slot: str, context: dict[str, Any] = None) -> None:
        """
        Fire all functions registered to a slot, in order of registration.

        The 'context' dict carries information about what happened:
            {"step": 2, "property": "out-of-service", "value": True}

        All registered functions receive this same context dict.
        """
        if context is None:
            context = {}

        handlers = self._registry.get(slot, [])
        if not handlers:
            return  # no one registered here — that's fine

        log.debug(f"Triggering hook '{slot}' → {len(handlers)} handler(s)")

        for fn in handlers:
            try:
                # Support both async and sync hook functions
                if asyncio.iscoroutinefunction(fn):
                    await fn(context)
                else:
                    fn(context)
            except Exception as hook_err:
                # A broken hook should NEVER crash the main test sequence
                log.warning(f"Hook '{slot}' → {fn.__name__}() raised: {hook_err}")


# =============================================================================
# The one HookManager instance the whole app uses
# Import with:  from core.hooks import hooks
# =============================================================================
hooks = HookManager()
