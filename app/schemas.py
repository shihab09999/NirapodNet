from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Literal

from .security import contains_control_characters


def _clean_text(value: str) -> str:
    """Strip surrounding whitespace and reject control characters.

    Applied to free-text fields so stored content cannot smuggle
    NUL/control bytes into the database or into other clients.
    Rendering already uses textContent on the frontend, so this
    is defence in depth, not the only XSS control.
    """
    cleaned = value.strip()

    if contains_control_characters(cleaned):
        raise ValueError("control characters are not allowed")

    return cleaned


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def username_must_be_clean(cls, value: str) -> str:
        cleaned = _clean_text(value)

        if len(cleaned) < 3:
            raise ValueError("username is too short")

        if any(char.isspace() for char in cleaned):
            raise ValueError("username must not contain whitespace")

        return cleaned


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

# NOTE: there is no separate RegisterRequest any more. Registration
# uses UserCreate everywhere (POST /users and POST /api/register);
# the old duplicate schema was dead code and is removed.
class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class LoginResponse(BaseModel):
    token: str
    user: UserResponse
    expires_at: datetime


class SessionResponse(BaseModel):
    """One login session, as listed for its owner.

    token_preview is only the first 8 characters of the stored
    SHA-256 token hash. The hash itself is never a usable token,
    and the preview is only enough to tell sessions apart in the
    list; revoking "all other sessions" does not need it at all.
    """

    token_preview: str
    expires_at: datetime

#-----------------
# Message Schemas
#-----------------

class MessageCreate(BaseModel):
    client_id: str = Field(min_length=1, max_length=100)
    # Audit fix (10): clients used to be required to send sender_id
    # even though the server always overwrote it with the
    # authenticated user. It is now optional and always ignored:
    # the sender is the logged-in user, never the request body.
    sender_id: int | None = None
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def content_must_be_clean(cls, value: str) -> str:
        cleaned = _clean_text(value)

        if not cleaned:
            raise ValueError("content must not be empty")

        return cleaned


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

    @field_validator("description")
    @classmethod
    def description_must_be_clean(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return _clean_text(value)


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

    @field_validator("type", "message")
    @classmethod
    def broadcast_fields_must_be_clean(cls, value: str) -> str:
        cleaned = _clean_text(value)

        if not cleaned:
            raise ValueError("field must not be empty")

        return cleaned


class BroadcastResponse(BaseModel):
    id: int
    issued_by: int
    type: str
    message: str
    priority: str
    created_at: datetime
    # Phase 3: None for broadcasts created before Phase 3.
    signature: str | None = None

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
