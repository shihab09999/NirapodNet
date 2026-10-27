# NirapodNet — API and Message Format

This document describes the local network communication protocol as
implemented in Phase 1 (core prototype) and Phase 2 (emergency
system). It covers the REST endpoints and the WebSocket message
formats. FastAPI also serves interactive documentation at `/docs`
while the server is running.

## Authentication

- Register: `POST /api/register` with `{"username", "password"}`
  (username 3–50 chars, password 8–128 chars). Returns `201`, or
  `409` when the username is taken.
- Login: `POST /api/login` with the same body. Returns
  `{"token", "user": {"id", "username", "role"}, "expires_at"}`.
  Sessions expire after 24 hours.
- Authenticated requests send the token as
  `Authorization: Bearer <token>`.
- Logout: `POST /api/logout` invalidates the current session.
- Current user: `GET /api/me`.

### Roles

| Role | Tier |
|------|------|
| `user` | Regular user |
| `rescue` / `responder` | Responder tier (same permissions; `responder` is the roadmap name, `rescue` the original name) |
| `operator` | Operator |
| `admin` | Administrator |

Only an admin can change roles:
`PATCH /api/admin/users/{user_id}/role` with `{"role": "<role>"}`.
The first admin is bootstrapped with the
`NIRAPODNET_ADMIN_USERNAME` and `NIRAPODNET_ADMIN_PASSWORD`
environment variables at server startup (password minimum 8
characters); without them, startup behaviour is unchanged.

## REST endpoints

| Method and path | Who | Purpose |
|---|---|---|
| `GET /` | public | Web UI |
| `GET /api` | public | System status |
| `POST /users` | public | Legacy Phase 1 user creation (idempotent, no session) |
| `POST /api/register` | public | Create an account |
| `POST /api/login` | public | Log in, returns a session token |
| `POST /api/logout` | any session | Log out |
| `GET /api/me` | any session | Current user |
| `GET /users`, `GET /api/admin/users` | admin | List users |
| `PATCH /api/admin/users/{user_id}/role` | admin | Change a user's role |
| `GET /api/rbac/user|rescue|operator|admin` | by tier | Role probe endpoints |
| `POST /messages` | any role | Post a message (sender is taken from the session) |
| `GET /messages` | any session | Message history, oldest first |
| `POST /api/sos` | any role | Create an SOS (see below) |
| `GET /api/sos?status=` | responder, operator, admin | List SOS incidents |
| `GET /api/sos/{incident_id}/history` | responder, operator, admin | SOS status history |
| `PATCH /api/sos/{incident_id}/status` | responder, operator, admin | Advance an SOS status |
| `POST /api/broadcasts` | operator, admin | Create an emergency broadcast |
| `GET /api/broadcasts?after_id=` | any session | List broadcasts (optionally only after an id) |
| `POST /api/checkins` | any session | Send a safety check-in |
| `GET /api/checkins/me` | any session | Own check-in history |
| `GET /api/checkins` | responder, operator, admin | All check-ins |
| `GET /api/checkins/summary` | responder, operator, admin | Per-status counts, latest check-in per user |
| `GET /api/audit-logs?limit=` | operator, admin | Audit log (1–500 entries) |

### SOS

Create body:

```json
{
  "emergency_type": "flood | medical | fire | trapped | other",
  "latitude": -90 to 90, or null,
  "longitude": -180 to 180, or null,
  "description": "optional, up to 2000 chars"
}
```

Each SOS gets an incident id (`INC-<year>-<5 digits>`) and starts as
`OPEN`. Status changes must follow
`OPEN → RESPONDING → ON-SCENE → RESOLVED`; any other transition is
rejected with `409`.

### Broadcasts

Create body:

```json
{
  "type": "e.g. Flood Warning",
  "message": "up to 5000 chars",
  "priority": "critical | high | medium | low"
}
```

`info` and `warning` are also accepted as legacy aliases from the
first Phase 2 iteration. In Phase 2 a broadcast targets the whole
local network; geographic targeting arrives with the geospatial
layer in Phase 6.

### Check-ins

Create body:

```json
{
  "status": "SAFE | NEED_HELP | NOT_AT_LOCATION | UNABLE_TO_RESPOND",
  "broadcast_id": "optional id of the broadcast being answered"
}
```

## WebSocket protocol

Connect with `ws://<host>:8000/ws?token=<session token>`. An
invalid or expired token closes the connection with code `1008`.

Client → server (chat message):

```json
{"client_id": "unique per message, 1-100 chars", "content": "1-2000 chars"}
```

Messages outside those limits are rejected with an error frame and
are not stored. A repeated `client_id` from the same sender returns
the original acknowledgement instead of storing a duplicate.

Server → client frames:

| `type` | Meaning | Extra fields |
|---|---|---|
| `ack` | Your message was stored | `client_id`, `message_id`, `sender_id`, `sender`, `content`, `timestamp` |
| `message` | Another user's message | `client_id`, `id`, `sender_id`, `sender`, `content`, `timestamp` |
| `sos` | New SOS (responder tier and above only) | `incident_id`, `user_id`, `emergency_type`, `latitude`, `longitude`, `description`, `status`, `created_at` |
| `sos_status` | SOS status changed (responder tier and above only) | `incident_id`, `status`, `changed_by`, `timestamp` |
| `broadcast` | New emergency broadcast (all users) | `id`, `broadcast_type`, `message`, `priority`, `issued_by`, `created_at` |
| `error` | Your last frame was invalid | `error` |
