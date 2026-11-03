from datetime import datetime, timezone
import secrets

from sqlalchemy.orm import Session, joinedload

from . import models, schemas
from .security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)

# Phase 3: keep at most this many live sessions per user. The
# oldest sessions are dropped when a new login would exceed it,
# so a stolen token does not stay usable forever alongside
# every later login.
MAX_SESSIONS_PER_USER = 5

#-----------------
# users
#-----------------

def create_user(db: Session, user: schemas.UserCreate):
    existing = (
        db.query(models.User)
        .filter(models.User.username == user.username)
        .first()
    )

    if existing:
        return existing

    db_user = models.User(
        username=user.username,
        password_hash=hash_password(user.password),
        role="user",
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user


def get_users(db: Session, limit: int = 100, offset: int = 0):
    # Audit fix (4): bounded lists. The old code returned every
    # row at once; every list endpoint now takes limit/offset
    # with a server-side cap, and the default is 100.
    return (
        db.query(models.User)
        .order_by(models.User.id.asc())
        .limit(limit)
        .offset(offset)
        .all()
    )


def list_sessions(db: Session, user_id: int):
    """Sessions of one user, newest expiry last, for /api/sessions."""
    return (
        db.query(models.UserSession)
        .filter(models.UserSession.user_id == user_id)
        .order_by(models.UserSession.expires_at.asc())
        .all()
    )


def delete_other_sessions(
    db: Session,
    user_id: int,
    current_token_hash: str,
):
    """Revoke every session of a user except the current one."""
    others = (
        db.query(models.UserSession)
        .filter(
            models.UserSession.user_id == user_id,
            models.UserSession.token != current_token_hash,
        )
        .all()
    )

    for session in others:
        db.delete(session)

    db.commit()

    return len(others)


def authenticate_user(
    db: Session,
    username: str,
    password: str,
):
    user = (
        db.query(models.User)
        .filter(models.User.username == username)
        .first()
    )

    if user is None:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user


def create_session(
    db: Session,
    user_id: int,
    expires_at: datetime,
):
    """Create a session and return (session, plain token).

    Only the SHA-256 hash of the token is stored. The plain
    token is returned once, to the login caller, and must be
    sent back as the Bearer token. It is never stored again.
    """
    token = generate_session_token()

    existing = (
        db.query(models.UserSession)
        .filter(models.UserSession.user_id == user_id)
        .order_by(models.UserSession.expires_at.asc())
        .all()
    )

    # Drop the oldest sessions first (earliest expiry first)
    # so that after the new session is added, at most
    # MAX_SESSIONS_PER_USER remain.
    excess = len(existing) - (MAX_SESSIONS_PER_USER - 1)

    for old in existing[:max(excess, 0)]:
        db.delete(old)

    session = models.UserSession(
        token=hash_session_token(token),
        user_id=user_id,
        expires_at=expires_at,
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return session, token


def get_session_user(
    db: Session,
    token: str,
):
    session = (
        db.query(models.UserSession)
        .filter(
            models.UserSession.token == hash_session_token(token)
        )
        .first()
    )

    if session is None:
        return None

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if session.expires_at <= now:
        db.delete(session)
        db.commit()
        return None

    return session.user


def delete_session(
    db: Session,
    token: str,
):
    session = (
        db.query(models.UserSession)
        .filter(
            models.UserSession.token == hash_session_token(token)
        )
        .first()
    )

    if session is None:
        return False

    db.delete(session)
    db.commit()

    return True


def delete_sessions_for_user(
    db: Session,
    user_id: int,
    commit: bool = True,
):
    """Phase 3: invalidate every session of a user.

    Used when an admin changes that user's role, so a token
    issued under the old role cannot keep being used.
    commit=False lets the caller commit role change, session
    invalidation and audit entry in one transaction (audit
    fix 10: audit atomicity), instead of three separate commits.
    """
    sessions = (
        db.query(models.UserSession)
        .filter(models.UserSession.user_id == user_id)
        .all()
    )

    for session in sessions:
        db.delete(session)

    if commit:
        db.commit()

    return len(sessions)


def get_idempotency_record(
    db: Session,
    user_id: int,
    endpoint: str,
    idempotency_key: str,
):
    return (
        db.query(models.IdempotencyRecord)
        .filter(
            models.IdempotencyRecord.user_id == user_id,
            models.IdempotencyRecord.endpoint == endpoint,
            models.IdempotencyRecord.idempotency_key
            == idempotency_key,
        )
        .first()
    )


def save_idempotency_record(
    db: Session,
    user_id: int,
    endpoint: str,
    idempotency_key: str,
    response_status: int,
    response_body: str,
):
    record = models.IdempotencyRecord(
        user_id=user_id,
        endpoint=endpoint,
        idempotency_key=idempotency_key,
        response_status=response_status,
        response_body=response_body,
    )

    db.add(record)
    db.commit()

    return record

#------------------
#Messages
#--------------------

def create_message(db: Session, message: schemas.MessageCreate):
    existing = (
        db.query(models.Message)
        .filter(
            models.Message.sender_id == message.sender_id,
            models.Message.client_id == message.client_id
        )
        .first()
    )

    if existing:
        return {
            "id": existing.id,
            "client_id": existing.client_id,
            "sender_id": existing.sender_id,
            "sender": existing.sender.username,
            "content": existing.content,
            "timestamp": existing.timestamp
        }

    db_message = models.Message(
        client_id=message.client_id,
        sender_id=message.sender_id,
        content=message.content,
    )

    db.add(db_message)
    db.commit()
    db.refresh(db_message)

    return {
        "id": db_message.id,
        "client_id": db_message.client_id,
        "sender_id": db_message.sender_id,
        "sender": db_message.sender.username,
        "content": db_message.content,
        "timestamp": db_message.timestamp
    }


def get_messages(db: Session, limit: int = 100, offset: int = 0):
    # Audit fix (4): bounded, and joinedload(sender) instead of
    # one sender query per message (the old N+1). This function
    # was previously dead code; GET /messages now uses it.
    messages = (
        db.query(models.Message)
        .options(joinedload(models.Message.sender))
        .order_by(models.Message.timestamp)
        .limit(limit)
        .offset(offset)
        .all()
    )

    return [
        {
            "id": m.id,
            "client_id": m.client_id,
            "sender_id": m.sender_id,
            "sender": m.sender.username,
            "content": m.content,
            "timestamp": m.timestamp
        }
        for m in messages
    ]


SOS_STATUSES = (
    "OPEN",
    "RESPONDING",
    "ON-SCENE",
    "RESOLVED",
)

ALLOWED_STATUS_TRANSITIONS = {
    "OPEN": {"RESPONDING"},
    "RESPONDING": {"ON-SCENE"},
    "ON-SCENE": {"RESOLVED"},
    "RESOLVED": set(),
}


def generate_incident_id(db: Session) -> str:
    year = datetime.now(timezone.utc).year

    while True:
        number = secrets.randbelow(100000)

        incident_id = f"INC-{year}-{number:05d}"

        existing = (
            db.query(models.SOSEvent)
            .filter(
                models.SOSEvent.incident_id == incident_id
            )
            .first()
        )

        if existing is None:
            return incident_id


def create_sos(
    db: Session,
    user_id: int,
    sos: schemas.SOSCreate,
    commit: bool = True,
):
    incident = models.SOSEvent(
        incident_id=generate_incident_id(db),
        user_id=user_id,
        emergency_type=sos.emergency_type,
        latitude=(
            str(sos.latitude)
            if sos.latitude is not None
            else None
        ),
        longitude=(
            str(sos.longitude)
            if sos.longitude is not None
            else None
        ),
        description=sos.description,
        status="OPEN",
    )

    db.add(incident)
    db.flush()

    history = models.SOSStatusHistory(
        incident_id=incident.id,
        old_status=None,
        new_status="OPEN",
        changed_by=user_id,
    )

    db.add(history)

    # Audit fix (10): commit=False lets the endpoint commit the
    # incident and its audit entry in one transaction, so a crash
    # cannot leave an SOS without its audit row (or vice versa).
    if commit:
        db.commit()
        db.refresh(incident)

    return incident


def get_sos_by_incident_id(
    db: Session,
    incident_id: str,
):
    return (
        db.query(models.SOSEvent)
        .filter(
            models.SOSEvent.incident_id == incident_id
        )
        .first()
    )


def update_sos_status(
    db: Session,
    incident: models.SOSEvent,
    new_status: str,
    changed_by: int,
    commit: bool = True,
):
    old_status = incident.status

    allowed_next_states = ALLOWED_STATUS_TRANSITIONS.get(
        old_status,
        set(),
    )

    if new_status not in allowed_next_states:
        return None

    incident.status = new_status

    history = models.SOSStatusHistory(
        incident_id=incident.id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
    )

    db.add(history)

    if commit:
        db.commit()
        db.refresh(incident)
    else:
        db.flush()

    return incident


def get_sos_events(
    db: Session,
    status_filter: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    query = (
        db.query(models.SOSEvent)
        .order_by(models.SOSEvent.created_at.asc())
    )

    if status_filter:
        query = query.filter(
            models.SOSEvent.status == status_filter
        )

    return query.limit(limit).offset(offset).all()


def get_sos_history(
    db: Session,
    incident: models.SOSEvent,
):
    return (
        db.query(models.SOSStatusHistory)
        .filter(
            models.SOSStatusHistory.incident_id
            == incident.id
        )
        .order_by(
            models.SOSStatusHistory.created_at.asc()
        )
        .all()
    )


def create_broadcast(
    db: Session,
    issued_by: int,
    broadcast: schemas.BroadcastCreate,
    commit: bool = True,
):
    db_broadcast = models.Broadcast(
        issued_by=issued_by,
        type=broadcast.type,
        message=broadcast.message,
        priority=broadcast.priority,
    )

    db.add(db_broadcast)

    if commit:
        db.commit()
        db.refresh(db_broadcast)
    else:
        db.flush()
        db.refresh(db_broadcast)

    return db_broadcast


def get_broadcasts(
    db: Session,
    after_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
):
    query = (
        db.query(models.Broadcast)
        .order_by(models.Broadcast.id.asc())
    )

    if after_id is not None:
        query = query.filter(
            models.Broadcast.id > after_id
        )

    return query.limit(limit).offset(offset).all()


# ------------------
# Check-Ins
# ------------------

def _checkin_to_dict(checkin: models.CheckIn) -> dict:
    return {
        "id": checkin.id,
        "user_id": checkin.user_id,
        "username": checkin.user.username,
        "status": checkin.status,
        "broadcast_id": checkin.broadcast_id,
        "created_at": checkin.created_at,
    }


def create_checkin(
    db: Session,
    user_id: int,
    checkin: schemas.CheckInCreate,
    commit: bool = True,
):
    if checkin.broadcast_id is not None:
        broadcast = (
            db.query(models.Broadcast)
            .filter(models.Broadcast.id == checkin.broadcast_id)
            .first()
        )

        if broadcast is None:
            return None

    db_checkin = models.CheckIn(
        user_id=user_id,
        status=checkin.status,
        broadcast_id=checkin.broadcast_id,
    )

    db.add(db_checkin)

    if commit:
        db.commit()
        db.refresh(db_checkin)
    else:
        db.flush()
        db.refresh(db_checkin)

    return _checkin_to_dict(db_checkin)


def get_user_checkins(
    db: Session,
    user_id: int,
    limit: int = 100,
    offset: int = 0,
):
    # joinedload(user): _checkin_to_dict reads username per row,
    # which was an N+1 before this fix.
    checkins = (
        db.query(models.CheckIn)
        .options(joinedload(models.CheckIn.user))
        .filter(models.CheckIn.user_id == user_id)
        .order_by(models.CheckIn.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return [_checkin_to_dict(c) for c in checkins]


def get_checkins(db: Session, limit: int = 100, offset: int = 0):
    checkins = (
        db.query(models.CheckIn)
        .options(joinedload(models.CheckIn.user))
        .order_by(models.CheckIn.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return [_checkin_to_dict(c) for c in checkins]


def get_checkin_summary(db: Session) -> dict:
    total_users = db.query(models.User).count()

    checkins = (
        db.query(models.CheckIn)
        .order_by(
            models.CheckIn.user_id.asc(),
            models.CheckIn.created_at.asc(),
        )
        .all()
    )

    # Only each user's latest check-in counts towards the summary.
    latest_by_user: dict[int, models.CheckIn] = {}

    for checkin in checkins:
        latest_by_user[checkin.user_id] = checkin

    counts = {status: 0 for status in schemas.CHECKIN_STATUSES}

    for checkin in latest_by_user.values():
        if checkin.status in counts:
            counts[checkin.status] += 1

    checked_in = len(latest_by_user)

    return {
        "total_users": total_users,
        "checked_in_users": checked_in,
        "not_checked_in_users": total_users - checked_in,
        "counts": counts,
    }


# ------------------
# Audit Log
# ------------------

def log_audit(
    db: Session,
    actor_id: int,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    detail: str | None = None,
    commit: bool = True,
):
    entry = models.AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail,
    )

    db.add(entry)

    if commit:
        db.commit()
        db.refresh(entry)
    else:
        db.flush()

    return entry


def get_audit_logs(
    db: Session,
    limit: int = 100,
):
    logs = (
        db.query(models.AuditLog)
        .options(joinedload(models.AuditLog.actor))
        .order_by(models.AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": entry.id,
            "actor_id": entry.actor_id,
            "actor": entry.actor.username,
            "action": entry.action,
            "entity_type": entry.entity_type,
            "entity_id": entry.entity_id,
            "detail": entry.detail,
            "created_at": entry.created_at,
        }
        for entry in logs
    ]
