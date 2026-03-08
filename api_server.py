"""
================================================================================
 api_server.py  —  FastAPI WebSocket bridge
================================================================================
 Sits between COV Monitor (BACnet) and React browser dashboard.
 Receives COV notifications via hooks, broadcasts to all browser clients.

 Install deps:  pip install fastapi uvicorn websockets
 Run with:      uvicorn api_server:app --reload
 Then open:     http://localhost:3000 (React frontend)
================================================================================
"""

"""
================================================================================
 api_server.py  —  FastAPI WebSocket bridge (v2 — robust WS handling)
================================================================================
 Install: pip install fastapi uvicorn websockets
 Run:     uvicorn api_server:app --reload
================================================================================
"""

import asyncio
import json
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    import asyncio.base_events
    asyncio.base_events._set_reuseport = lambda sock: None
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config.settings import cfg
from core.hooks import hooks
from core.cov_monitor import COVMonitor

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api_server")


# =============================================================================
# CONNECTION MANAGER
# =============================================================================

class ConnectionManager:
    def __init__(self):
        self.clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.append(ws)
        log.info(f"Browser connected — total clients: {len(self.clients)}")

    def disconnect(self, ws: WebSocket):
        if ws in self.clients:
            self.clients.remove(ws)
        log.info(f"Browser disconnected — total clients: {len(self.clients)}")

    async def broadcast(self, message: dict):
        if not self.clients:
            return
        text = json.dumps(message)
        dead = []
        for ws in self.clients:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# =============================================================================
# LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg.dut.port            = 62856   # ⚠ update from Yabe after every restart
    cfg.cov.lifetime        = 300
    cfg.cov.log_to_csv      = True
    cfg.cov.show_live_table = False

    @hooks.register("on_cov")
    async def broadcast_to_browsers(ctx):
        notif = ctx["notification"]
        await manager.broadcast({
            "object_id": notif.object_id,
            "label":     notif.label,
            "value":     notif.value,
            "unit":      notif.unit,
            "in_alarm":  notif.in_alarm,
            "ts":        notif.timestamp.isoformat(),
        })

    monitor = COVMonitor(cfg=cfg, hooks=hooks)
    async def run_with_recovery():
        while True:
            try:
                await monitor.run()
            except Exception as e:
                log.warning(f"COV monitor crashed: {e} — restarting in 5s...")
                await asyncio.sleep(5)

    asyncio.create_task(run_with_recovery())
    
    log.info("COV monitor started as background task")
    yield
    log.info("Server shutting down")


# =============================================================================
# APP
# =============================================================================

app = FastAPI(title="BACnet Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "BACnet Dashboard API running"}


@app.get("/health")
async def health():
    return {
        "status":  "ok",
        "clients": len(manager.clients),
        "dut":     f"{cfg.dut.ip}:{cfg.dut.port}",
        "targets": len(cfg.cov.cov_targets),
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive()
            if data.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning(f"WebSocket error: {e}")
    finally:
        manager.disconnect(ws)