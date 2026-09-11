"""WS /ws: live signal broadcast (adapted w/ permission from
Hash-sudo-cell/scalping-arise app/api/v1/websocket.py). Late joiners get
signal history + a hello; clients may ping/subscribe."""
from __future__ import annotations
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["stream"])
_connections: set[WebSocket] = set()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    from app.core.bus import get_bus
    await ws.accept()
    _connections.add(ws)
    bus = get_bus()
    try:
        for ev in bus.history("signal", limit=10):
            await ws.send_text(json.dumps(ev, default=str))
        await ws.send_text(json.dumps({"type": "connected",
                                       "message": "XAU/USD live signal stream",
                                       "clients": len(_connections)}))
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _connections.discard(ws)


@router.get("/live/status", tags=["stream"])
def live_status():
    from app.live.manager import get_manager
    return get_manager().status()


@router.post("/live/start", tags=["stream"])
async def live_start():
    from app.live.manager import get_manager
    await get_manager().start()
    return get_manager().status()


@router.post("/live/stop", tags=["stream"])
async def live_stop():
    from app.live.manager import get_manager
    await get_manager().stop()
    return get_manager().status()


def broadcast(event: dict) -> None:
    """Sync fan-out helper (called from async context via bus subscriber)."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    msg = json.dumps(event, default=str)
    for ws in list(_connections):
        loop.create_task(_safe_send(ws, msg))


async def _safe_send(ws: WebSocket, msg: str) -> None:
    try:
        await ws.send_text(msg)
    except Exception:
        _connections.discard(ws)
