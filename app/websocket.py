import secrets
import time

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[WebSocket, int] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self.active_connections[websocket] = user_id

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            del self.active_connections[websocket]

    async def broadcast(
        self,
        message: dict,
        exclude: WebSocket | None = None
    ):
        disconnected = []

        for connection in self.active_connections:
            if connection is exclude:
                continue

            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for connection in disconnected:
            self.disconnect(connection)


manager = ConnectionManager()

# Audit fix (3): one-time WebSocket tickets. The old frontend sent
# the long-lived session token in the WebSocket URL
# (/ws?token=...), and uvicorn's access log prints the full request
# path, so the token landed in logs. A ticket is different: it is
# single-use, expires 60 seconds after issue, and is bound to the
# session it was issued from. A ticket found in a log after use is
# already dead, and a ticket issued from a session that has since
# been revoked or expired is rejected on every message, not just
# at connect time (see the per-message check in app/main.py).
_WS_TICKET_TTL_SECONDS = 60
_ws_tickets: dict[str, dict] = {}


def issue_ws_ticket(user_id: int, session_token_hash: str) -> str:
    """Create a single-use ticket for one WebSocket connection."""
    ticket = secrets.token_urlsafe(32)
    _ws_tickets[ticket] = {
        "user_id": user_id,
        "session_token_hash": session_token_hash,
        "expires_at": time.time() + _WS_TICKET_TTL_SECONDS,
    }
    return ticket


def redeem_ws_ticket(ticket: str):
    """Consume a ticket, returning its payload or None.

    Redeeming removes the ticket whether it was valid or expired,
    so a captured ticket cannot be replayed after its first use.
    """
    payload = _ws_tickets.pop(ticket, None)

    if payload is None:
        return None

    if payload["expires_at"] < time.time():
        return None

    return payload
