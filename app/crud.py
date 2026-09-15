from datetime import datetime, timezone
import secrets

from sqlalchemy.orm import Session

from . import models, schemas
from .security import generate_session_token, hash_password, verify_password

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


def get_users(db: Session):
    return db.query(models.User).all()


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
    token = generate_session_token()

    session = models.UserSession(
        token=token,
        user_id=user_id,
        expires_at=expires_at,
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return session


def get_session_user(
    db: Session,
    token: str,
):
    session = (
        db.query(models.UserSession)
        .filter(models.UserSession.token == token)
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
        .filter(models.UserSession.token == token)
        .first()
    )

    if session is None:
        return False

    db.delete(session)
    db.commit()

    return True

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


def get_messages(db: Session):
    messages = (
        db.query(models.Message)
        .order_by(models.Message.timestamp)
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
    db.commit()
    db.refresh(incident)

    return incident


def get_sos_events(
    db: Session,
    status_filter: str | None = None,
):
    query = (
        db.query(models.SOSEvent)
        .order_by(models.SOSEvent.created_at.asc())
    )

    if status_filter:
        query = query.filter(
            models.SOSEvent.status == status_filter
        )

    return query.all()


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
):
    db_broadcast = models.Broadcast(
        issued_by=issued_by,
        type=broadcast.type,
        message=broadcast.message,
        priority=broadcast.priority,
    )

    db.add(db_broadcast)
    db.commit()
    db.refresh(db_broadcast)

    return db_broadcast


def get_broadcasts(
    db: Session,
    after_id: int | None = None,
):
    query = (
        db.query(models.Broadcast)
        .order_by(models.Broadcast.id.asc())
    )

    if after_id is not None:
        query = query.filter(
            models.Broadcast.id > after_id
        )

    return query.all()
