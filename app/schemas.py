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

    latitude: float | None = None
    longitude: float | None = None

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
    priority: Literal["info", "warning", "critical"]


class BroadcastResponse(BaseModel):
    id: int
    issued_by: int
    type: str
    message: str
    priority: str
    created_at: datetime

    class Config:
        from_attributes = True
