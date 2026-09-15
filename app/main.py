from pathlib import Path
from fastapi import FastAPI, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.security import (HTTPAuthorizationCredentials,HTTPBearer,)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Query, status
from .dependencies import require_role
from .auth import get_current_user

from .database import engine, get_db
from .models import Base
from . import schemas, crud

from fastapi import WebSocket, WebSocketDisconnect
from .websocket import manager
from .database import SessionLocal
from .models import (Base,User,Message,UserSession,SOSEvent,Broadcast,CheckIn,)
from .dependencies import ALL_ROLES, require_role, ADMIN_ROLE
BASE_DIR = Path(__file__).resolve().parent

security = HTTPBearer()

app = FastAPI(title="NirapodNet")

# Create SQLite tables on startup
Base.metadata.create_all(bind=engine)

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
    credentials: schemas.LoginRequest,
    db: Session = Depends(get_db),
):
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

    session = crud.create_session(
        db,
        user_id=user.id,
        expires_at=expires_at,
    )

    return {
        "token": session.token,
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

    return user


@app.get("/api/rbac/user")
def rbac_user_test(
    current_user: User = Depends(
        require_role(
            "user",
            "rescue",
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
            "operator",
            "admin",
        )
    ),
):
    message.sender_id = current_user.id

    return crud.create_message(db, message)


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
            "operator",
            "admin",
        )
    ),
):
    incident = crud.create_sos(
        db=db,
        user_id=current_user.id,
        sos=sos,
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

    for connection in manager.active_connections:
        try:
            await connection.send_json(message)
        except Exception:
            disconnected.append(connection)

    for connection in disconnected:
        manager.disconnect(connection)


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

        while True:
            data = await websocket.receive_json()

            client_id = data.get("client_id")
            content = data.get("content")

            if not client_id or not content:
                await websocket.send_json({
                    "type": "error",
                    "error": "Invalid message",
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