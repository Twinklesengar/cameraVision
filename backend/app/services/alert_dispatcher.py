import asyncio
import json
from typing import List
from fastapi import WebSocket


class AlertDispatcher:
    """Thread-safe WebSocket alert broadcaster.

    `broadcast_sync` may be called from any thread (camera workers, generators);
    it schedules the fan-out on the main FastAPI event loop.
    """

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def _broadcast(self, payload: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    def broadcast_sync(self, alert_data: dict):
        payload = json.dumps(alert_data)
        if self._loop is not None and self.active_connections:
            try:
                asyncio.run_coroutine_threadsafe(self._broadcast(payload), self._loop)
            except RuntimeError:
                pass

    @property
    def client_count(self) -> int:
        return len(self.active_connections)


alert_dispatcher = AlertDispatcher()