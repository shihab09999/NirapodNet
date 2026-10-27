from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: int
    username: str = Field(min_length=3, max_length=50)
    role: str

    class Config:
        from_attributes = True


class RoleUpdate(BaseModel):
    role: str


# -----------------
# Authentication
# -----------------

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class LoginResponse(BaseModel):
    token: str
    user: UserResponse
    expires_at: datetime

#-----------------
# Message Schemas
#-----------------

class MessageCreate(BaseModel):
    client_id: str = Field(min_length=1, max_length=100)
    sender_id: int
    content: str = Field(min_length=1, max_length=2000)


class MessageResponse(BaseModel):
    id: int
    client_id: str = Field(min_length=1, max_length=100)
    sender_id: int
    sender: str
    content: str = Field(min_length=1, max_length=2000)
    timestamp: datetime

    class Config:
        from_attributes = True


class SOSCreate(BaseModel):
    emergency_type: Literal[
        "flood",
        "medical",
        "fire",
        "trapped",
        "other",
    ]

    latitude: float | None = Field(
        default=None,
        ge=-90,
        le=90,
    )
    longitude: float | None = Field(
        default=None,
        ge=-180,
        le=180,
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
    )


class SOSStatusUpdate(BaseModel):
    status: Literal[
        "RESPONDING",
        "ON-SCENE",
        "RESOLVED",
    ]


class SOSStatusHistoryResponse(BaseModel):
    old_status: str | None
    new_status: str
    changed_by: int
    created_at: datetime

    class Config:
        from_attributes = True


class SOSResponse(BaseModel):
    id: int
    incident_id: str
    user_id: int
    emergency_type: str
    latitude: float | None
    longitude: float | None
    description: str | None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class BroadcastCreate(BaseModel):
    type: str = Field(min_length=1, max_length=50)
    message: str = Field(min_length=1, max_length=5000)
    # Roadmap levels are critical/high/medium/low; info/warning are
    # kept as accepted aliases from the first Phase 2 iteration so
    # broadcasts already stored with those values stay valid.
    priority: Literal[
        "critical",
        "high",
        "medium",
        "low",
        "info",
        "warning",
    ]


class BroadcastResponse(BaseModel):
    id: int
    issued_by: int
    type: str
    message: str
    priority: str
    created_at: datetime

    class Config:
        from_attributes = True


# -----------------
# Check-In Schemas
# -----------------

CHECKIN_STATUSES = (
    "SAFE",
    "NEED_HELP",
    "NOT_AT_LOCATION",
    "UNABLE_TO_RESPOND",
)


class CheckInCreate(BaseModel):
    status: Literal[
        "SAFE",
        "NEED_HELP",
        "NOT_AT_LOCATION",
        "UNABLE_TO_RESPOND",
    ]
    broadcast_id: int | None = None


class CheckInResponse(BaseModel):
    id: int
    user_id: int
    username: str
    status: str
    broadcast_id: int | None
    created_at: datetime

    class Config:
        from_attributes = True


class CheckInSummaryResponse(BaseModel):
    total_users: int
    checked_in_users: int
    not_checked_in_users: int
    counts: dict[str, int]


# -----------------
# Audit Log Schemas
# -----------------

class AuditLogResponse(BaseModel):
    id: int
    actor_id: int
    actor: str
    action: str
    entity_type: str
    entity_id: str | None
    detail: str | None
    created_at: datetime

    class Config:
        from_attributes = True
