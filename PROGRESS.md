# NirapodNet — Progress Log

## Overview
This document serves as a chronological work history and project diary for NirapodNet. Each entry records the date, phase, tasks completed, decisions made, blockers encountered, and next steps.

---

## 2026-08-17 — Project Initialization

**Phase:** 0 — Foundation  
**Status:** In Progress

### Tasks Completed
- [x] Created project repository structure
- [x] Created README.md with project overview, architecture, and quick start
- [x] Copied MASTER_PLAN.md to docs/MASTER_PLAN.md (complete project specification)
- [x] Created ROADMAP.md with 14 phases and detailed task breakdowns
- [x] Created PROGRESS.md (this file)
- [x] Created .gitignore for Python, Node, IDE, and environment files
- [x] Created LICENSE (MIT License)

### Decisions Made
- Project structure follows the recommended repository layout
- Documentation organized in docs/ directory
- MIT License chosen for open-source portfolio project
- Roadmap structured around 14 phases matching MASTER_PLAN.md

### Blockers
- None at this stage

### Next Steps
- Initialize Git repository
- Set up Python virtual environment
- Create initial project structure (backend/, frontend/, docker-compose.yml)
- Begin Phase 1: Core Prototype implementation

---

## 2026-10-20 — Phase 2 Completion

**Phase:** 2 — Emergency System
**Status:** Completed

### Tasks Completed
- [x] Emergency Broadcast completed: `POST /api/broadcasts` for operators/admins, live WebSocket delivery to all connected users, and the frontend's missing `syncMissedBroadcasts()` implemented so missed broadcasts are fetched with `after_id` after a reconnect
- [x] Safety Check-In completed: `POST /api/checkins` with the four statuses (SAFE, NEED_HELP, NOT_AT_LOCATION, UNABLE_TO_RESPOND), optional link to a broadcast, per-user history (`GET /api/checkins/me`), operator list and an aggregation summary that counts only each user's latest check-in
- [x] Operator/admin dashboard UI added to the existing page: SOS incident list with status-advance buttons, broadcast composer, check-in summary, and audit log view (operator/admin only)
- [x] Audit logging added for critical actions: role changes, SOS creation, SOS status changes, broadcast creation, and check-ins (`GET /api/audit-logs`, operator/admin only)
- [x] First-admin bootstrap added: `NIRAPODNET_ADMIN_USERNAME` / `NIRAPODNET_ADMIN_PASSWORD` environment variables create or promote the first admin at startup; without them startup behaviour is unchanged
- [x] Frontend login flow fixed to use the Phase 2 auth system (`/api/register` + `/api/login` with a password field); the old flow called `/users` with only a username and could no longer log in
- [x] Check-in panel added to the frontend with the four status buttons
- [x] `pwdlib[argon2]` pinned to `==0.3.1` in requirements.txt (it was the only unpinned dependency)
- [x] Phase 2 test log written: `tests/phase-2-test-log.md`

### Decisions Made
- Broadcast priority levels stay as implemented and used by the frontend/CSS: info, warning, critical
- The broadcast WebSocket payload uses `type: "broadcast"` for routing and `broadcast_type` for the broadcast's own type, matching the existing frontend handler
- Audit logging is a new table only; no existing table was altered, so databases created by earlier phases upgrade automatically on startup (verified in the test log)
- Geographic targeting for broadcasts is deferred to Phase 6 (Geospatial Layer): user areas/locations do not exist before that phase, and phases proceed serially. In Phase 2 a broadcast targets the whole local network. The ROADMAP checkbox stays open until Phase 6
- Phase 1 behaviour was preserved and all Phase 1 tests were re-run as regression tests and pass. (Correction, added at the hard check below: Phase 1 *code* was not literally untouched — the frontend login flow, template and CSS changed where Phase 2 authentication required it.)

### Blockers
- None

### Metrics
- 36/36 automated checks passed (authentication, RBAC, broadcast, SOS, check-in, audit, WebSocket, Phase 1 regression)
- Existing-database upgrade test passed (old data preserved, new table auto-created)
- Real uvicorn run passed

### Next Steps
- Phase 3 — Security, in serial order (nothing from Phase 3 was started in this phase)

---

## 2026-10-20 — Phase 2 Hard Check

**Phase:** 2 — Emergency System
**Status:** Completed (verified)

An independent static audit plus a separate adversarial test run
(37 checks) were performed against the completion claim above.
The audit corroborated the core claim (broadcast, check-in, SOS
lifecycle, RBAC enforcement, password hashing, audit-log
existence), and the adversarial run initially failed 5 checks.
All of the following were found and fixed the same day:

- The roadmap's "Responder" role could not be assigned at all
  (400). `responder` is now accepted everywhere the `rescue` tier
  is, and existing `rescue` accounts are unaffected
- SOS latitude/longitude accepted any value (e.g. 999). Range
  validation added (-90..90, -180..180; out-of-range returns 422)
- The roadmap's broadcast priority levels (Critical, High,
  Medium, Low) were not accepted (422). They are now implemented
  end to end; info/warning remain as legacy aliases
- The WebSocket path ignored the REST message limits: a
  5000-character message and a 300-character client_id were
  stored. The WebSocket handler now enforces the same
  1-2000 / 1-100 limits and replies with an error frame
- The SOS form hardcoded type "other", null coordinates and a
  fixed description. The form now has a type selector, a
  description field, and best-effort browser geolocation
- `syncMissedBroadcasts()` silently dropped all but the newest
  missed broadcast. Every missed broadcast is now also added to
  the message list as a system notice
- A check-in could stay silently linked to a broadcast banner
  that had been acknowledged or hidden. The link is now cleared
  on acknowledge and only used while the banner is visible
- The dashboard had no admin functions and no session handling.
  It now includes admin user/role management, a recent check-in
  list, SOS history, a logout button, and session restore via
  `GET /api/me`
- The admin bootstrap wrote no audit entry. It now records an
  `admin_bootstrapped` audit event (create and promote)
- The completion evidence lived outside the repo. The automated
  suite is now committed as `tests/run_phase2_checks.py`
  (44/44 passing) and the protocol is documented in
  `docs/API.md`

Re-verification after the fixes: committed suite 44/44, the
original Phase 2 suite 36/36, the adversarial suite 37/37, the
existing-database upgrade test, and a real uvicorn run all pass.

Remaining known items, deliberately not hidden: audit entries
are written in a second commit after the action (not one
transaction); Phase 1's Docker Compose checkbox stays open;
broadcast geographic targeting stays deferred to Phase 6.

---

## Template for Future Entries

### YYYY-MM-DD — Descriptive Title

**Phase:** X — Phase Name  
**Status:** Not Started / In Progress / Completed / Blocked

### Tasks Completed
- [ ] Task description
- [ ] Task description

### Decisions Made
- Key architectural or technical decisions
- Tool/technology selections
- Scope changes

### Blockers
- Description of blocker
- Impact assessment
- Mitigation plan

### Metrics (if applicable)
- Performance measurements
- Test results
- User feedback scores

### Next Steps
- Immediate next tasks
- Upcoming milestones

---

## Phase Completion Log

| Phase | Start Date | End Date | Status | Notes |
|-------|------------|----------|--------|-------|
| Phase 0 — Foundation | 2026-08-17 | 2026-08-30 | Completed | Repository and environment set up; superseded by Phase 1 completion |
| Phase 1 — Core Prototype | 2026-08-20 | 2026-08-31 | Completed | 5/5 tests in tests/phase-1 test log; behaviour unchanged by Phase 2 work |
| Phase 2 — Emergency System | 2026-09-01 | 2026-10-20 | Completed | Broadcast, check-in, dashboard and audit completed 2026-10-20; see tests/phase-2-test-log.md. Broadcast geographic targeting deferred to Phase 6 |
| Phase 3 — Security | - | - | Not Started | - |
| Phase 4 — Measurement | - | - | Not Started | - |
| Phase 5 — First Real Pilot | - | - | Not Started | - |
| Phase 6 — Geospatial Layer | - | - | Not Started | - |
| Phase 7 — Sensor Network | - | - | Not Started | - |
| Phase 8 — Resilient Networking | - | - | Not Started | - |
| Phase 9 — Portable Infrastructure | - | - | Not Started | - |
| Phase 10 — UAV Integration | - | - | Not Started | - |
| Phase 11 — Satellite Backhaul | - | - | Not Started | - |
| Phase 12 — Multi-Node Deployment | - | - | Not Started | - |
| Phase 13 — Research & Validation | - | - | Not Started | - |

---

## Key Decisions Log

| Date | Decision | Rationale | Impact |
|------|----------|-----------|--------|
| 2026-08-17 | Use MIT License | Open-source portfolio project, maximum adoption | Permissive, allows commercial use |
| 2026-08-17 | Python/FastAPI backend | Team familiarity, rich ecosystem, async support | Fast development, good WebSocket support |
| 2026-08-17 | HTML/CSS/JS frontend (no framework initially) | Simplicity, offline-first, no build step required | Lightweight, works offline, easy to deploy |
| 2026-08-17 | SQLite for edge storage | Zero-config, file-based, portable | Ideal for disconnected edge nodes |
| 2026-08-17 | 14-phase roadmap | Matches MASTER_PLAN.md structure | Clear progression, measurable milestones |

---

## Blocker History

| Date | Blocker | Phase | Resolution | Resolution Date |
|------|---------|-------|------------|-----------------|
| - | - | - | - | - |

---

## Meeting Notes

### 2026-08-17 — Project Kickoff
**Attendees:** Project Lead  
**Summary:** Initialized repository with core documentation files. Established project structure and roadmap. Ready to begin Phase 0 foundation work.

**Action Items:**
- [ ] Initialize Git repository
- [ ] Set up development environment
- [ ] Create initial backend/frontend structure

---

*This progress log should be updated at the end of each work session. Each entry should be honest about challenges, not just successes.*