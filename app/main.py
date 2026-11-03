from pathlib import Path
from fastapi import FastAPI, Request, Depends, Query, Header
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
)
from starlette.background import BackgroundTask
from fastapi.security import (HTTPAuthorizationCredentials,HTTPBearer,)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import json
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Query, status
from .dependencies import require_role
from .auth import get_current_user
from .rate_limit import limiter
from .security import (
    broadcast_canonical_string,
    hash_session_token,
    sign_broadcast,
    verify_broadcast_signature,
)

from .database import DATABASE_URL, engine, get_db
from .models import Base
from . import schemas, crud

from fastapi import WebSocket, WebSocketDisconnect
from .websocket import (
    issue_ws_ticket,
    manager,
    redeem_ws_ticket,
)
from .database import SessionLocal
from .models import (Base,User,Message,UserSession,SOSEvent,Broadcast,CheckIn,AuditLog,)
from .dependencies import ALL_ROLES, require_role, ADMIN_ROLE
BASE_DIR = Path(__file__).resolve().parent

security = HTTPBearer()

app = FastAPI(title="NirapodNet")

# Phase 3: security headers on every response. CSP keeps
# script-src to 'self' (the template loads only /static/app.js);
# style-src keeps 'unsafe-inline' because the template itself
# uses inline style attributes for show/hide -- removing those
# attributes is a follow-up, not a silent break of the UI.
# HSTS is only sent over HTTPS: sending it over plain LAN HTTP
# would tell browsers to force HTTPS on later visits and break
# the plain-HTTP LAN deployment.
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(self)"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self' ws: wss:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


def _client_ip(request: Request) -> str:
    # TestClient and direct LAN clients have no trusted proxy
    # in front of them, so X-Forwarded-For is never trusted:
    # it is client-controlled and would let an attacker rotate
    # rate-limit keys at will.
    if request.client is not None:
        return request.client.host

    return "unknown"


def _check_write_rate_limit(user: User):
    # 120 writes per minute per user: far above normal emergency
    # use, far below a flooding client. Phase 2 regression
    # traffic stays well under this.
    if not limiter.allow(f"write:{user.id}", 120, 60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )


def _idempotency_replay(db: Session, user: User, endpoint: str, key):
    """Return a stored replay response, or None to proceed."""
    if not key:
        return None

    record = crud.get_idempotency_record(db, user.id, endpoint, key)

    if record is None:
        return None

    return JSONResponse(
        status_code=record.response_status,
        content=json.loads(record.response_body),
    )


def _save_idempotency(db: Session, user: User, endpoint: str, key,
                      status_code: int, body: dict):
    if not key:
        return

    existing = crud.get_idempotency_record(db, user.id, endpoint, key)

    if existing is not None:
        return

    crud.save_idempotency_record(
        db,
        user_id=user.id,
        endpoint=endpoint,
        idempotency_key=key,
        response_status=status_code,
        response_body=json.dumps(body),
    )


def _sign_broadcast(db: Session, created):
    """Sign a broadcast and persist its signature."""
    canonical = broadcast_canonical_string(
        created.id,
        created.issued_by,
        created.type,
        created.message,
        created.priority,
        created.created_at.isoformat(),
    )
    created.signature = sign_broadcast(canonical)
    db.commit()
    db.refresh(created)
    return created

# Create SQLite tables on startup
Base.metadata.create_all(bind=engine)


def _migrate_broadcast_signature():
    """Phase 3 upgrade: add Broadcast.signature to old databases.

    create_all only creates missing tables, it never adds a
    column to an existing table. Without this migration, a
    database created before Phase 3 would fail every
    broadcast query with "no such column: signature".
    New databases already have the column, so this is a
    no-op for them.
    """
    with engine.connect() as conn:
        columns = [
            row[1]
            for row in conn.exec_driver_sql(
                "PRAGMA table_info(broadcasts)"
            )
        ]

        if columns and "signature" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE broadcasts "
                "ADD COLUMN signature VARCHAR(128)"
            )
            conn.commit()


_migrate_broadcast_signature()


def _bootstrap_admin():
    """Create the first admin account from environment variables.

    Set NIRAPODNET_ADMIN_USERNAME and NIRAPODNET_ADMIN_PASSWORD before
    starting the server to bootstrap the first admin. Without both
    variables this is a no-op, so existing deployments are unaffected.
    The password is never changed for an account that already exists;
    an existing account with the bootstrap username is only promoted
    to the admin role.
    """
    import os

    from .security import hash_password

    username = os.environ.get("NIRAPODNET_ADMIN_USERNAME", "").strip()
    password = os.environ.get("NIRAPODNET_ADMIN_PASSWORD", "")

    if not username or len(password) < 8:
        return

    db = SessionLocal()

    try:
        existing = (
            db.query(User)
            .filter(User.username == username)
            .first()
        )

        if existing is None:
            admin = User(
                username=username,
                password_hash=hash_password(password),
                role=ADMIN_ROLE,
            )
            db.add(admin)
            db.flush()
            db.add(
                AuditLog(
                    actor_id=admin.id,
                    action="admin_bootstrapped",
                    entity_type="user",
                    entity_id=str(admin.id),
                    detail="admin account created via environment bootstrap",
                )
            )
            db.commit()
        elif existing.role != ADMIN_ROLE:
            existing.role = ADMIN_ROLE
            db.add(
                AuditLog(
                    actor_id=existing.id,
                    action="admin_bootstrapped",
                    entity_type="user",
                    entity_id=str(existing.id),
                    detail="account promoted to admin via environment bootstrap",
                )
            )
            db.commit()
    finally:
        db.close()


_bootstrap_admin()

# Static files
app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static"
)

templates = Jinja2Templates(directory=BASE_DIR / "templates")

# -----------------------
# HTML Pages
# -----------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


# -----------------------
# System API
# -----------------------

@app.get("/api")
def api_status():
    return {
        "system": "NirapodNet",
        "status": "online"
    }


# -----------------------
# User API
# -----------------------

@app.post("/users", response_model=schemas.UserResponse)
def create_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    return crud.create_user(db, user)


@app.post(
    "/api/register",
    response_model=schemas.UserResponse,
    status_code=201,
)
def register_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
):
    existing = (
        db.query(User)
        .filter(User.username == user.username)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    return crud.create_user(db, user)


@app.post(
    "/api/login",
    response_model=schemas.LoginResponse,
)
def login_user(
    request: Request,
    credentials: schemas.LoginRequest,
    db: Session = Depends(get_db),
):
    # Phase 3: count every login attempt, success or not, per
    # IP + username. The limit is env-tunable for tests; the
    # default (10/minute) is high enough for normal use and
    # low enough to slow credential stuffing on one account
    # without blocking other accounts on the same LAN IP.
    login_limit = int(
        os.environ.get("NIRAPODNET_LOGIN_RATE_LIMIT", "10")
    )
    login_key = f"login:{_client_ip(request)}:{credentials.username}"

    if not limiter.allow(login_key, login_limit, 60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts",
            headers={"Retry-After": "60"},
        )

    user = crud.authenticate_user(
        db,
        credentials.username,
        credentials.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(hours=24)
    )

    session, token = crud.create_session(
        db,
        user_id=user.id,
        expires_at=expires_at,
    )

    return {
        "token": token,
        "user": user,
        "expires_at": session.expires_at,
    }


@app.post("/api/logout")
def logout_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    token = credentials.credentials

    crud.delete_session(db, token)

    return {
        "message": "Logged out successfully"
    }


@app.get(
    "/api/me",
    response_model=schemas.UserResponse,
)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user


@app.get(
    "/users",
    response_model=list[schemas.UserResponse],
)
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends
    (require_role("admin")
     ),
):
    return crud.get_users(db)


@app.get(
    "/api/admin/users",
    response_model=list[schemas.UserResponse],
)
def list_admin_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(ADMIN_ROLE)),
):
    return crud.get_users(db)


@app.patch(
    "/api/admin/users/{user_id}/role",
    response_model=schemas.UserResponse,
)
def update_user_role(
    user_id: int,
    role_update: schemas.RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(ADMIN_ROLE)),
):
    if role_update.role not in ALL_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role",
        )

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.role = role_update.role

    db.commit()
    db.refresh(user)

    # Phase 3: a token issued under the old role must not keep
    # working. All of this user's sessions are invalidated, so
    # the user must log in again under the new role.
    crud.delete_sessions_for_user(db, user.id)

    crud.log_audit(
        db,
        actor_id=current_user.id,
        action="user_role_updated",
        entity_type="user",
        entity_id=str(user.id),
        detail=f"{user.username} role set to {user.role}",
    )

    return user


@app.get("/api/rbac/user")
def rbac_user_test(
    current_user: User = Depends(
        require_role(
            "user",
            "rescue",
            "responder",
            "operator",
            "admin",
        )
    ),
):
    return {
        "message": "User-level access granted",
        "user": current_user.username,
        "role": current_user.role,
    }


@app.get("/api/rbac/rescue")
def rbac_rescue_test(
    current_user: User = Depends(
        require_role(
            "rescue",
            "responder",
            "operator",
            "admin",
        )
    ),
):
    return {
        "message": "Rescue-level access granted",
        "user": current_user.username,
        "role": current_user.role,
    }


@app.get("/api/rbac/operator")
def rbac_operator_test(
    current_user: User = Depends(
        require_role(
            "operator",
            "admin",
        )
    ),
):
    return {
        "message": "Operator-level access granted",
        "user": current_user.username,
        "role": current_user.role,
    }


@app.get("/api/rbac/admin")
def rbac_admin_test(
    current_user: User = Depends(
        require_role("admin")
    ),
):
    return {
        "message": "Admin-level access granted",
        "user": current_user.username,
        "role": current_user.role,
    }


# -----------------------
# Message API
# -----------------------

@app.post("/messages", response_model=schemas.MessageResponse)
def create_message(
    message: schemas.MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            "user",
            "rescue",
            "responder",
            "operator",
            "admin",
        )
    ),
    idempotency_key: str | None = Header(default=None),
):
    _check_write_rate_limit(current_user)

    replay = _idempotency_replay(
        db, current_user, "POST /messages", idempotency_key
    )

    if replay is not None:
        return replay

    message.sender_id = current_user.id

    created = crud.create_message(db, message)
    body = schemas.MessageResponse.model_validate(created).model_dump(
        mode="json"
    )
    _save_idempotency(
        db, current_user, "POST /messages", idempotency_key, 200, body
    )

    return created


@app.get("/messages", response_model=list[schemas.MessageResponse])
def list_messages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    messages = (
        db.query(Message)
        .order_by(Message.timestamp.asc())
        .all()
    )

    return [
        {
            "id": message.id,
            "client_id": message.client_id,
            "sender_id": message.sender_id,
            "sender": message.sender.username,
            "content": message.content,
            "timestamp": message.timestamp.isoformat(),
        }
        for message in messages
    ]


@app.post(
    "/api/sos",
    response_model=schemas.SOSResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sos(
    sos: schemas.SOSCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            "user",
            "rescue",
            "responder",
            "operator",
            "admin",
        )
    ),
    idempotency_key: str | None = Header(default=None),
):
    _check_write_rate_limit(current_user)

    replay = _idempotency_replay(
        db, current_user, "POST /api/sos", idempotency_key
    )

    if replay is not None:
        return replay

    incident = crud.create_sos(
        db=db,
        user_id=current_user.id,
        sos=sos,
    )

    crud.log_audit(
        db,
        actor_id=current_user.id,
        action="sos_created",
        entity_type="sos",
        entity_id=incident.incident_id,
        detail=f"emergency_type={incident.emergency_type}",
    )

    await broadcast_sos(
        db,
        {
            "type": "sos",
            "incident_id": incident.incident_id,
            "user_id": incident.user_id,
            "emergency_type": incident.emergency_type,
            "latitude": (
                float(incident.latitude)
                if incident.latitude is not None
                else None
            ),
            "longitude": (
                float(incident.longitude)
                if incident.longitude is not None
                else None
            ),
            "description": incident.description,
            "status": incident.status,
            "created_at": incident.created_at.isoformat(),
        },
    )

    body = schemas.SOSResponse.model_validate(incident).model_dump(
        mode="json"
    )
    _save_idempotency(
        db, current_user, "POST /api/sos", idempotency_key, 201, body
    )

    return incident


@app.get(
    "/api/sos",
    response_model=list[schemas.SOSResponse],
)
def list_sos(
    status_filter: str | None = Query(
        default=None,
        alias="status",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            "rescue",
            "responder",
            "operator",
            "admin",
        )
    ),
):
    allowed_statuses = {
        "OPEN",
        "RESPONDING",
        "ON-SCENE",
        "RESOLVED",
    }

    if (
        status_filter is not None
        and status_filter not in allowed_statuses
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid SOS status",
        )

    return crud.get_sos_events(
        db,
        status_filter=status_filter,
    )


@app.get(
    "/api/sos/{incident_id}/history",
    response_model=list[schemas.SOSStatusHistoryResponse],
)
def get_sos_history(
    incident_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            "rescue",
            "responder",
            "operator",
            "admin",
        )
    ),
):
    incident = crud.get_sos_by_incident_id(
        db,
        incident_id,
    )

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SOS incident not found",
        )

    return crud.get_sos_history(
        db,
        incident,
    )


@app.patch(
    "/api/sos/{incident_id}/status",
    response_model=schemas.SOSResponse,
)
async def update_sos_status(
    incident_id: str,
    update: schemas.SOSStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            "rescue",
            "responder",
            "operator",
            "admin",
        )
    ),
):
    incident = crud.get_sos_by_incident_id(
        db,
        incident_id,
    )

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SOS incident not found",
        )

    updated = crud.update_sos_status(
        db=db,
        incident=incident,
        new_status=update.status,
        changed_by=current_user.id,
    )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invalid SOS status transition",
        )

    crud.log_audit(
        db,
        actor_id=current_user.id,
        action="sos_status_changed",
        entity_type="sos",
        entity_id=updated.incident_id,
        detail=f"status set to {updated.status}",
    )

    await broadcast_sos(
        db,
        {
            "type": "sos_status",
            "incident_id": updated.incident_id,
            "status": updated.status,
            "changed_by": current_user.id,
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
        },
    )

    return updated


async def broadcast_sos(
    db: Session,
    message: dict,
):
    disconnected = []

    for connection, user_id in manager.active_connections.items():
        recipient = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if recipient is None:
            continue

        if recipient.role not in {
            "rescue",
            "responder",
            "operator",
            "admin",
        }:
            continue

        try:
            await connection.send_json(message)
        except Exception:
            disconnected.append(connection)

    for connection in disconnected:
        manager.disconnect(connection)


async def broadcast_alert(message: dict):
    disconnected = []

    for connection in list(manager.active_connections.keys()):
        try:
            await connection.send_json(message)
        except Exception:
            disconnected.append(connection)

    for connection in disconnected:
        manager.disconnect(connection)


@app.post(
    "/api/broadcasts",
    response_model=schemas.BroadcastResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_broadcast(
    broadcast: schemas.BroadcastCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            "operator",
            "admin",
        )
    ),
    idempotency_key: str | None = Header(default=None),
):
    _check_write_rate_limit(current_user)

    replay = _idempotency_replay(
        db, current_user, "POST /api/broadcasts", idempotency_key
    )

    if replay is not None:
        return replay

    created = crud.create_broadcast(
        db,
        issued_by=current_user.id,
        broadcast=broadcast,
    )

    # Phase 3: sign the broadcast before it is delivered.
    created = _sign_broadcast(db, created)

    crud.log_audit(
        db,
        actor_id=current_user.id,
        action="broadcast_created",
        entity_type="broadcast",
        entity_id=str(created.id),
        detail=(
            f"type={created.type} "
            f"priority={created.priority}"
        ),
    )

    await broadcast_alert(
        {
            "type": "broadcast",
            "id": created.id,
            "broadcast_type": created.type,
            "message": created.message,
            "priority": created.priority,
            "issued_by": created.issued_by,
            "created_at": created.created_at.isoformat(),
            "signature": created.signature,
        }
    )

    body = schemas.BroadcastResponse.model_validate(
        created
    ).model_dump(mode="json")
    _save_idempotency(
        db, current_user, "POST /api/broadcasts",
        idempotency_key, 201, body,
    )

    return created


@app.get(
    "/api/broadcasts",
    response_model=list[schemas.BroadcastResponse],
)
def list_broadcasts(
    after_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_broadcasts(
        db,
        after_id=after_id,
    )


@app.get("/api/broadcasts/{broadcast_id}/verify")
def verify_broadcast(
    broadcast_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Phase 3: check a stored broadcast's HMAC signature.

    Returns valid=False for broadcasts created before Phase 3
    (no signature stored) and for any broadcast whose stored
    fields no longer match its signature.
    """
    broadcast = (
        db.query(Broadcast)
        .filter(Broadcast.id == broadcast_id)
        .first()
    )

    if broadcast is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Broadcast not found",
        )

    canonical = broadcast_canonical_string(
        broadcast.id,
        broadcast.issued_by,
        broadcast.type,
        broadcast.message,
        broadcast.priority,
        broadcast.created_at.isoformat(),
    )

    return {
        "id": broadcast.id,
        "signature_present": broadcast.signature is not None,
        "valid": verify_broadcast_signature(
            canonical, broadcast.signature
        ),
    }


# -----------------------
# Check-In API
# -----------------------

@app.post(
    "/api/checkins",
    response_model=schemas.CheckInResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_checkin(
    checkin: schemas.CheckInCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None),
):
    _check_write_rate_limit(current_user)

    replay = _idempotency_replay(
        db, current_user, "POST /api/checkins", idempotency_key
    )

    if replay is not None:
        return replay

    created = crud.create_checkin(
        db,
        user_id=current_user.id,
        checkin=checkin,
    )

    if created is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Broadcast not found",
        )

    crud.log_audit(
        db,
        actor_id=current_user.id,
        action="checkin_created",
        entity_type="checkin",
        entity_id=str(created["id"]),
        detail=f"status={created['status']}",
    )

    body = schemas.CheckInResponse.model_validate(
        created
    ).model_dump(mode="json")
    _save_idempotency(
        db, current_user, "POST /api/checkins",
        idempotency_key, 201, body,
    )

    return created


@app.get(
    "/api/checkins/me",
    response_model=list[schemas.CheckInResponse],
)
def list_my_checkins(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_user_checkins(
        db,
        user_id=current_user.id,
    )


@app.get(
    "/api/checkins/summary",
    response_model=schemas.CheckInSummaryResponse,
)
def get_checkin_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            "rescue",
            "responder",
            "operator",
            "admin",
        )
    ),
):
    return crud.get_checkin_summary(db)


@app.get(
    "/api/checkins",
    response_model=list[schemas.CheckInResponse],
)
def list_checkins(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            "rescue",
            "responder",
            "operator",
            "admin",
        )
    ),
):
    return crud.get_checkins(db)


# -----------------------
# Audit Log API
# -----------------------

@app.get(
    "/api/audit-logs",
    response_model=list[schemas.AuditLogResponse],
)
def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            "operator",
            "admin",
        )
    ),
):
    return crud.get_audit_logs(
        db,
        limit=limit,
    )


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
):
    db = SessionLocal()

    try:
        user = crud.get_session_user(db, token)

        if user is None:
            await websocket.close(code=1008)
            return

        await manager.connect(
            websocket,
            user.id,
        )

        # Phase 3: optional per-connection replay protection.
        # seq/ts are optional so Phase 1/2 clients that send
        # only client_id+content keep working; when a client
        # does send them, they are enforced strictly.
        last_seq: int | None = None

        while True:
            data = await websocket.receive_json()

            # Phase 3: 30 messages per 10 seconds per connection.
            if not limiter.allow(
                f"ws:{id(websocket)}", 30, 10
            ):
                await websocket.send_json({
                    "type": "error",
                    "error": "Rate limit exceeded",
                })
                continue

            client_id = data.get("client_id")
            content = data.get("content")

            # Mirror the REST MessageCreate limits so the WebSocket
            # path cannot store values the API schema would reject
            # (content 1-2000 chars, client_id 1-100 chars).
            if (
                not isinstance(client_id, str)
                or not isinstance(content, str)
                or not 1 <= len(client_id) <= 100
                or not 1 <= len(content) <= 2000
            ):
                await websocket.send_json({
                    "type": "error",
                    "error": "Invalid message",
                })
                continue

            # Phase 3 replay checks, only when the client sends
            # these fields. Control characters are also rejected
            # here, matching the REST schema validators.
            from .security import contains_control_characters

            if contains_control_characters(content):
                await websocket.send_json({
                    "type": "error",
                    "error": "Invalid message",
                })
                continue

            if "seq" in data:
                seq = data.get("seq")

                if (
                    not isinstance(seq, int)
                    or isinstance(seq, bool)
                    or (
                        last_seq is not None and seq <= last_seq
                    )
                ):
                    await websocket.send_json({
                        "type": "error",
                        "error": "Stale or replayed sequence",
                    })
                    continue

                last_seq = seq

            if "ts" in data:
                ts = data.get("ts")

                if (
                    not isinstance(ts, (int, float))
                    or isinstance(ts, bool)
                    or abs(time.time() - float(ts)) > 300
                ):
                    await websocket.send_json({
                        "type": "error",
                        "error": "Stale timestamp",
                    })
                    continue

            existing = (
                db.query(Message)
                .filter(
                    Message.sender_id == user.id,
                    Message.client_id == client_id,
                )
                .first()
            )

            if existing:
                await websocket.send_json({
                    "type": "ack",
                    "client_id": client_id,
                    "message_id": existing.id,
                    "sender_id": existing.sender_id,
                    "sender": existing.sender.username,
                    "content": existing.content,
                    "timestamp": existing.timestamp.isoformat(),
                })
                continue

            message = Message(
                client_id=client_id,
                sender_id=user.id,
                content=content,
            )

            db.add(message)
            db.commit()
            db.refresh(message)

            await websocket.send_json({
                "type": "ack",
                "client_id": client_id,
                "message_id": message.id,
                "sender_id": user.id,
                "sender": user.username,
                "content": content,
                "timestamp": message.timestamp.isoformat(),
            })

            await manager.broadcast(
                {
                    "type": "message",
                    "client_id": client_id,
                    "id": message.id,
                    "sender": user.username,
                    "sender_id": user.id,
                    "content": content,
                    "timestamp": message.timestamp.isoformat(),
                },
                exclude=websocket,
            )

    except WebSocketDisconnect:
        manager.disconnect(websocket)

    finally:
        db.close()