"""
================================================================================
 core/transport.py  —  THE NETWORK LAYER
================================================================================

 ARCHITECTURE LESSON 3: Separation of Concerns (SoC)
 ─────────────────────────────────────────────────────
 Each file/class should do ONE thing and do it well.
 This is called the "Single Responsibility Principle" (SRP).

 This file's ONE job: talk to the BACnet network.
 It does NOT know about:
   - what test values to inject (that's TestRunner's job)
   - what hooks to fire    (that's HookManager's job)
   - what config to use   (passed in from outside)

 Analogy — Restaurant Kitchen:
   Chef (TestRunner)  → decides WHAT dish to make
   Waiter (Transport) → carries food to the table (network)
   Manager (HookManager) → handles alerts and notifications
   Menu (Config)      → defines what's available

   The waiter doesn't decide the menu. The chef doesn't carry plates.
   Each role is clean and swappable.

 In industry this is called "Layered Architecture":
   ┌──────────────────────────────────┐
   │  Layer 4: Tests / Business Logic │  ← what to test
   ├──────────────────────────────────┤
   │  Layer 3: Core / Orchestration   │  ← how to run tests
   ├──────────────────────────────────┤
   │  Layer 2: Transport / Network    │  ← how to send packets  ← YOU ARE HERE
   ├──────────────────────────────────┤
   │  Layer 1: Config                 │  ← what settings to use
   └──────────────────────────────────┘

================================================================================
"""

import asyncio
import logging
import sys

log = logging.getLogger("testbench.transport")

# =============================================================================
# 🚨 WINDOWS + PYTHON 3.13 HOTFIX
# Placed here because this file owns all network concerns.
# Must happen before bacpypes3 imports.
# =============================================================================
if sys.platform == "win32":
    import asyncio.base_events
    asyncio.base_events._set_reuseport = lambda sock: None
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from bacpypes3.ipv4.app import NormalApplication
from bacpypes3.local.device import DeviceObject
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import Real, Boolean, ObjectIdentifier
from bacpypes3.basetypes import PropertyIdentifier

from config.settings import NetworkConfig


class BACnetTransport:
    """
    Wraps bacpypes3's NormalApplication with a clean, simple interface.

    ARCHITECTURE LESSON: Wrapper / Adapter Pattern
    ───────────────────────────────────────────────
    bacpypes3's API is powerful but verbose:
      await app.write_property(TARGET, OBJ_ID, PropertyIdentifier("present-value"), Real(31.0), priority=8)

    Our wrapper exposes a simpler interface:
      await transport.write("present-value", 31.0, priority=8)

    Benefits:
    1. If bacpypes3 changes its API in a future version, you fix it in ONE place here.
       All your tests keep working unchanged.
    2. Tests read like plain English, not low-level library calls.
    3. You can swap bacpypes3 for a different BACnet library later —
       just rewrite this file. Everything above it stays the same.

    This pattern is called "Adapter" or "Facade".
    """

    def __init__(self, net_cfg: NetworkConfig):
        self._cfg    = net_cfg
        self._app    = None      # NormalApplication — created in connect()
        self._target = None      # Address — set in connect()

    # ── ARCHITECTURE: Context Manager ─────────────────────────────────────────
    # The 'async with' pattern (context manager) guarantees cleanup.
    # Even if an exception crashes your code mid-test, __aexit__ always runs.
    # This is how you guarantee sockets are always closed.
    #
    # Usage:
    #   async with BACnetTransport(cfg) as transport:
    #       await transport.write(...)
    #   # socket is guaranteed closed here, even if exception was thrown

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
        return False  # don't suppress exceptions

    async def connect(self) -> None:
        """Instantiate NormalApplication and bind the UDP socket."""
        device = DeviceObject(
            objectIdentifier=("device", self._cfg.device_id),
            objectName=self._cfg.device_name,
            vendorIdentifier=self._cfg.vendor_id,
        )
        local_addr = Address(f"{self._cfg.local_ip}:{self._cfg.local_port}")
        self._app  = NormalApplication(device, local_addr)
        log.info(f"Transport bound to {self._cfg.local_ip}:{self._cfg.local_port}")

    async def disconnect(self) -> None:
        """Release the UDP socket gracefully."""
        if self._app:
            self._app.close()
            self._app = None
            log.info("Transport disconnected — sockets closed")

    # ── Write helper ──────────────────────────────────────────────────────────

    async def write(
        self,
        target:   Address,
        obj_id:   ObjectIdentifier,
        prop:     str,
        value:    float | bool,
        priority: int | None = None,
    ) -> None:
        """
        Send a WriteProperty request.

        Args:
            target:   Address("192.168.100.183:63205")
            obj_id:   ObjectIdentifier("analog-value,0")
            prop:     "present-value" or "out-of-service"
            value:    31.0 or True/False
            priority: 1-16 or None for non-commandable properties
        """
        # ── ARCHITECTURE: Type dispatch ───────────────────────────────────────
        # BACnet needs typed values (Real, Boolean), not raw Python types.
        # This mapping lives here so test code just passes 31.0 or True.
        bacnet_value = self._encode(value)

        kwargs = {}
        if priority is not None:
            kwargs["priority"] = priority

        await self._app.write_property(
            target,
            obj_id,
            PropertyIdentifier(prop),
            bacnet_value,
            **kwargs,
        )
        log.debug(f"WRITE {prop} = {value} (priority={priority}) → {target}")

    # ── Read helper ───────────────────────────────────────────────────────────

    async def read(
        self,
        target: Address,
        obj_id: ObjectIdentifier,
        prop:   str,
    ):
        """
        Send a ReadProperty request and return the decoded value.

        Args:
            target:  Address("192.168.100.183:63205")
            obj_id:  ObjectIdentifier("analog-value,0")
            prop:    "present-value" or "out-of-service"

        Returns:
            float, bool, or str depending on the property
        """
        result = await self._app.read_property(
            target,
            obj_id,
            PropertyIdentifier(prop),
        )
        log.debug(f"READ  {prop} = {result} ← {target}")
        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _encode(value: float | bool):
        """Convert Python native types to bacpypes3 typed primitives."""
        if isinstance(value, bool):
            return Boolean(value)
        if isinstance(value, (int, float)):
            return Real(float(value))
        raise TypeError(f"Unsupported value type: {type(value)}. Use float or bool.")

    @staticmethod
    def make_address(ip: str, port: int) -> Address:
        """Convenience factory — builds an Address from separate ip/port."""
        return Address(f"{ip}:{port}")

    @staticmethod
    def make_object_id(type_name: str, instance: int) -> ObjectIdentifier:
        """Convenience factory — builds an ObjectIdentifier."""
        return ObjectIdentifier(f"{type_name},{instance}")
