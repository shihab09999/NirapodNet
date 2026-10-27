# NirapodNet — Phase 2 Test Log

**Date:** 2026-10-20
**Phase:** Phase 2 — Emergency System
**Environment:** Linux + Python virtual environment (automated checks with FastAPI TestClient and a real uvicorn run)

## Phase 1 Regression

All Phase 1 behaviour was re-tested against the Phase 2 code:

* `GET /api` and homepage load — PASS
* `POST /users` still works and stays idempotent — PASS
* REST message create/history with the sender forced to the
  authenticated user — PASS
* WebSocket round trip: ACK to the sender, message to the other
  client, duplicate `client_id` returns the same message id — PASS
* Real uvicorn server start, homepage and static files served — PASS

## Test 1 — Authentication and Roles

**Tests:**

* Register a new user, duplicate register returns 409.
* Login with a wrong password returns 401.
* A normal user cannot change roles or list SOS incidents (403).

**Result:** PASS

## Test 2 — Admin Bootstrap

**Test:** Start the server with `NIRAPODNET_ADMIN_USERNAME` and
`NIRAPODNET_ADMIN_PASSWORD` set, then log in as that admin and
promote another user to operator. Start again without the variables
and confirm no account is created.

**Result:** PASS

## Test 3 — Emergency Broadcast

**Tests:**

* A normal user creating a broadcast returns 403.
* An operator creating a broadcast returns 201.
* An invalid priority returns 422.
* A connected user receives the broadcast live over WebSocket with
  `type: "broadcast"` and the broadcast's own type in
  `broadcast_type`.
* `GET /api/broadcasts?after_id=<id>` returns only broadcasts the
  client has not seen yet (used by the frontend's
  `syncMissedBroadcasts()` after a reconnect).

**Result:** PASS

## Test 4 — SOS Regression

**Tests:**

* A user creates an SOS (201, incident id assigned).
* An operator moves it OPEN → RESPONDING.
* Invalid transitions and normal-user access are still rejected.

**Result:** PASS

## Test 5 — Safety Check-In

**Tests:**

* Check in as SAFE with a broadcast id (201).
* An invalid status returns 422; an unknown broadcast id returns 404.
* A second check-in (NEED_HELP) becomes the user's latest status.
* `GET /api/checkins/me` returns the full history (2 entries).
* The operator summary counts only the latest check-in per user
  (NEED_HELP = 1, SAFE = 0, checked-in users = 1).
* A normal user cannot read the summary (403).

**Result:** PASS

## Test 6 — Audit Log

**Test:** After a role change, an SOS creation, an SOS status change,
broadcast creations and check-ins, read `GET /api/audit-logs` as an
operator and confirm all of those actions were recorded. A normal
user gets 403.

**Result:** PASS

## Test 7 — Existing Database Upgrade

**Test:** Create a database with the pre-Phase-2-completion code
(register, message, SOS), then run the new code against that same
database file.

**Expected:** Existing users can still log in, old messages and SOS
data are preserved, the new `audit_logs` table is created
automatically, and check-ins work. No existing table is altered.

**Result:** PASS

## Phase 2 Final Status

**Status:** COMPLETE

36/36 automated checks passed, plus the database upgrade test and a
real uvicorn run.

**Known deferral:** Broadcast geographic targeting is not part of
this phase's completed scope. User locations and areas belong to
Phase 6 (Geospatial Layer); in Phase 2 a broadcast targets the whole
local network, which matches the MASTER_PLAN wording "designated
network or geographic area". It stays unchecked in ROADMAP.md until
Phase 6.

## Hard Check Addendum (2026-10-20)

The completion claim above was re-checked the same day with an
independent static audit of the code and plan, plus a separate
adversarial test run (37 checks: full RBAC matrix, invalid SOS
transitions, invalid inputs, tampered tokens, SQL-injection-style
login, WebSocket abuse). The adversarial run initially failed 5
checks:

1. The roadmap's "Responder" role could not be assigned (400).
2. SOS latitude/longitude had no range validation (999 accepted).
3. The roadmap's priority level "high" was rejected (422).
4. A 5000-character WebSocket message was stored (REST limit 2000).
5. A 300-character WebSocket `client_id` was stored (REST limit 100).

All five were fixed, together with further audit findings (SOS form
hardcoding, missed broadcasts being dropped, stale check-in
broadcast linkage, missing admin UI/logout/session restore, and
the bootstrap writing no audit entry). The automated suite is now
committed to the repo as `tests/run_phase2_checks.py`.

**Re-verification result:** committed suite 44/44 PASS, original
Phase 2 suite 36/36 PASS, adversarial suite 37/37 PASS,
existing-database upgrade test PASS, real uvicorn run PASS.
