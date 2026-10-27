from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    username = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash = Column(
        String(255),
        nullable=False,
    )

    role = Column(
        String(20),
        nullable=False,
        default="user",
        index=True,
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    messages = relationship(
        "Message",
        back_populates="sender",
    )

    sessions = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    sos_events = relationship(
        "SOSEvent",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    broadcasts = relationship(
        "Broadcast",
        back_populates="issuer",
    )

    checkins = relationship(
        "CheckIn",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    audit_logs = relationship(
        "AuditLog",
        back_populates="actor",
        cascade="all, delete-orphan",
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)

    client_id = Column(
        String(100),
        nullable=False,
        index=True,
    )

    sender_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    content = Column(
        Text,
        nullable=False,
    )

    timestamp = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    sender = relationship(
        "User",
        back_populates="messages",
    )

    __table_args__ = (
        UniqueConstraint(
            "sender_id",
            "client_id",
            name="uq_message_sender_client",
        ),
    )


class UserSession(Base):
    __tablename__ = "sessions"

    token = Column(
        String(255),
        primary_key=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    expires_at = Column(
        DateTime,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="sessions",
    )


class SOSEvent(Base):
    __tablename__ = "sos_events"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    incident_id = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    emergency_type = Column(
        String(30),
        nullable=False,
    )

    latitude = Column(
        String(50),
        nullable=True,
    )

    longitude = Column(
        String(50),
        nullable=True,
    )

    description = Column(
        Text,
        nullable=True,
    )

    status = Column(
        String(20),
        nullable=False,
        default="OPEN",
        index=True,
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    user = relationship(
        "User",
        back_populates="sos_events",
    )

    status_history = relationship(
        "SOSStatusHistory",
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="SOSStatusHistory.created_at",
    )


class SOSStatusHistory(Base):
    __tablename__ = "sos_status_history"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    incident_id = Column(
        Integer,
        ForeignKey("sos_events.id"),
        nullable=False,
        index=True,
    )

    old_status = Column(
        String(20),
        nullable=True,
    )

    new_status = Column(
        String(20),
        nullable=False,
    )

    changed_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    incident = relationship(
        "SOSEvent",
        back_populates="status_history",
    )

    changed_by_user = relationship(
        "User",
        foreign_keys=[changed_by],
    )


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    issued_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    type = Column(
        String(50),
        nullable=False,
    )

    message = Column(
        Text,
        nullable=False,
    )

    priority = Column(
        String(20),
        nullable=False,
        default="info",
        index=True,
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    issuer = relationship(
        "User",
        back_populates="broadcasts",
    )

    checkins = relationship(
        "CheckIn",
        back_populates="broadcast",
    )


class CheckIn(Base):
    __tablename__ = "checkins"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    status = Column(
        String(30),
        nullable=False,
    )

    broadcast_id = Column(
        Integer,
        ForeignKey("broadcasts.id"),
        nullable=True,
        index=True,
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    user = relationship(
        "User",
        back_populates="checkins",
    )

    broadcast = relationship(
        "Broadcast",
        back_populates="checkins",
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    actor_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    action = Column(
        String(50),
        nullable=False,
        index=True,
    )

    entity_type = Column(
        String(50),
        nullable=False,
    )

    entity_id = Column(
        String(50),
        nullable=True,
    )

    detail = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    actor = relationship(
        "User",
        back_populates="audit_logs",
    )