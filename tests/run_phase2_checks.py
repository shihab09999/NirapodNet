"""NirapodNet automated checks (Phase 1 regression + Phase 2).

Run from the repository root with the project dependencies plus
httpx and websockets installed:

    pip install -r requirements.txt httpx websockets
    python tests/run_phase2_checks.py

The script uses a temporary database and a bootstrap admin created
through the NIRAPODNET_ADMIN_* environment variables, so it never
touches a real nirapodnet.db. It exits with code 0 only when every
check passes.
"""

import os
import sys
import tempfile

# Environment must be set before importing the app: the database URL
# and the admin bootstrap are both read at import/startup time.
_tmpdir = tempfile.mkdtemp(prefix="nirapodnet-checks-")
os.environ["NIRAPODNET_DB"] = "sqlite:///" + os.path.join(
    _tmpdir, "test.db"
)
os.environ["NIRAPODNET_ADMIN_USERNAME"] = "bossadmin"
os.environ["NIRAPODNET_ADMIN_PASSWORD"] = "adminpass123"

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

try:
    from fastapi.testclient import TestClient
except ImportError:
    print("httpx is required: pip install httpx websockets")
    raise

from app.main import app  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name} {detail}")


with TestClient(app, raise_server_exceptions=False) as c:
    # ---------- Phase 1 regression ----------
    r = c.get("/api")
    check("P1 /api online", r.status_code == 200)
    r = c.get("/")
    check("P1 homepage loads", r.status_code == 200)
    r = c.post(
        "/users",
        json={"username": "legacyuser", "password": "password123"},
    )
    check("P1 POST /users still works", r.status_code == 200)
    first_id = r.json()["id"]
    r = c.post(
        "/users",
        json={"username": "legacyuser", "password": "password123"},
    )
    check(
        "P1 POST /users idempotent",
        r.status_code == 200 and r.json()["id"] == first_id,
    )

    # ---------- Auth / bootstrap ----------
    r = c.post(
        "/api/register",
        json={"username": "victim", "password": "password123"},
    )
    check("register victim", r.status_code == 201)
    vid = r.json()["id"]
    r = c.post(
        "/api/register",
        json={"username": "victim", "password": "password123"},
    )
    check("register duplicate -> 409", r.status_code == 409)
    r = c.post(
        "/api/login",
        json={"username": "victim", "password": "wrongpass1"},
    )
    check("login wrong password -> 401", r.status_code == 401)
    r = c.post(
        "/api/login",
        json={"username": "victim", "password": "password123"},
    )
    vt = r.json()["token"]
    HV = {"Authorization": f"Bearer {vt}"}
    check("login victim", r.status_code == 200)

    r = c.post(
        "/api/login",
        json={"username": "bossadmin", "password": "adminpass123"},
    )
    check(
        "bootstrap admin login + role",
        r.status_code == 200
        and r.json()["user"]["role"] == "admin",
    )
    HA = {"Authorization": f"Bearer {r.json()['token']}"}

    r = c.post(
        "/api/register",
        json={"username": "operator1", "password": "password123"},
    )
    oid = r.json()["id"]
    r = c.patch(
        f"/api/admin/users/{oid}/role",
        headers=HA,
        json={"role": "operator"},
    )
    check("admin promotes operator", r.status_code == 200)
    r = c.patch(
        f"/api/admin/users/{oid}/role",
        headers=HV,
        json={"role": "admin"},
    )
    check("non-admin cannot promote -> 403", r.status_code == 403)
    r = c.post(
        "/api/login",
        json={"username": "operator1", "password": "password123"},
    )
    HO = {"Authorization": f"Bearer {r.json()['token']}"}

    # The roadmap's "Responder" name must work like "rescue".
    r = c.post(
        "/api/register",
        json={"username": "responder1", "password": "password123"},
    )
    rid = r.json()["id"]
    r = c.patch(
        f"/api/admin/users/{rid}/role",
        headers=HA,
        json={"role": "responder"},
    )
    check("role 'responder' assignable", r.status_code == 200)
    r = c.post(
        "/api/login",
        json={"username": "responder1", "password": "password123"},
    )
    HR = {"Authorization": f"Bearer {r.json()['token']}"}
    r = c.get("/api/sos", headers=HR)
    check("responder can list SOS", r.status_code == 200)

    # ---------- Messages (Phase 1 regression) ----------
    r = c.post(
        "/messages",
        headers=HV,
        json={
            "client_id": "m1",
            "sender_id": 999,
            "content": "hello",
        },
    )
    check(
        "P1 REST message, sender forced to session user",
        r.status_code == 200 and r.json()["sender_id"] == vid,
    )
    r = c.get("/messages", headers=HV)
    check(
        "P1 message history",
        r.status_code == 200 and len(r.json()) >= 1,
    )

    # ---------- Broadcast ----------
    r = c.post(
        "/api/broadcasts",
        headers=HV,
        json={
            "type": "Flood Warning",
            "message": "Move to shelter",
            "priority": "critical",
        },
    )
    check("broadcast by user -> 403", r.status_code == 403)
    r = c.post(
        "/api/broadcasts",
        headers=HO,
        json={
            "type": "Flood Warning",
            "message": "Move to shelter",
            "priority": "critical",
        },
    )
    check("broadcast by operator -> 201", r.status_code == 201)
    bid = r.json()["id"]
    r = c.post(
        "/api/broadcasts",
        headers=HO,
        json={"type": "T", "message": "m", "priority": "high"},
    )
    check(
        "broadcast roadmap priority 'high' -> 201",
        r.status_code == 201,
    )
    r = c.post(
        "/api/broadcasts",
        headers=HO,
        json={"type": "T", "message": "m", "priority": "urgent"},
    )
    check("broadcast invalid priority -> 422", r.status_code == 422)
    r = c.get("/api/broadcasts", headers=HV)
    check(
        "broadcast list",
        r.status_code == 200 and len(r.json()) >= 2,
    )
    r = c.get(
        f"/api/broadcasts?after_id={bid + 1}", headers=HV
    )
    check(
        "broadcast after_id sync",
        r.status_code == 200 and len(r.json()) == 0,
    )

    # ---------- WebSocket (Phase 1 regression + broadcast) ----------
    try:
        with c.websocket_connect(f"/ws?token={vt}") as ws_v:
            with c.websocket_connect(
                f"/ws?token={HO['Authorization'][7:]}"
            ) as ws_o:
                r = c.post(
                    "/api/broadcasts",
                    headers=HO,
                    json={
                        "type": "Fire Alert",
                        "message": "Evacuate now",
                        "priority": "warning",
                    },
                )
                check("second broadcast -> 201", r.status_code == 201)
                data = ws_v.receive_json()
                check(
                    "WS live broadcast received",
                    data.get("type") == "broadcast"
                    and data.get("broadcast_type") == "Fire Alert",
                )
                ws_o.receive_json()  # operator's own broadcast copy
                ws_v.send_json(
                    {"client_id": "w1", "content": "ws hello"}
                )
                ack = ws_v.receive_json()
                check("P1 WS ack", ack.get("type") == "ack")
                msg = ws_o.receive_json()
                check(
                    "P1 WS peer message",
                    msg.get("type") == "message"
                    and msg.get("content") == "ws hello",
                )
                ws_v.send_json(
                    {"client_id": "w2", "content": "x" * 5000}
                )
                err = ws_v.receive_json()
                check(
                    "WS oversized content -> error frame",
                    err.get("type") == "error",
                )
                ws_v.send_json(
                    {"client_id": "y" * 300, "content": "hi"}
                )
                err = ws_v.receive_json()
                check(
                    "WS oversized client_id -> error frame",
                    err.get("type") == "error",
                )
    except Exception as exc:  # noqa: BLE001
        check("WS flow", False, repr(exc))

    # ---------- SOS ----------
    r = c.post(
        "/api/sos",
        headers=HV,
        json={
            "emergency_type": "flood",
            "latitude": 999,
            "longitude": 90.4,
        },
    )
    check("SOS latitude out of range -> 422", r.status_code == 422)
    r = c.post(
        "/api/sos",
        headers=HV,
        json={
            "emergency_type": "flood",
            "latitude": 23.7,
            "longitude": 90.4,
            "description": "help",
        },
    )
    check("SOS create", r.status_code == 201)
    inc = r.json()["incident_id"]
    r = c.patch(
        f"/api/sos/{inc}/status",
        headers=HO,
        json={"status": "RESOLVED"},
    )
    check("SOS OPEN->RESOLVED -> 409", r.status_code == 409)
    r = c.patch(
        f"/api/sos/{inc}/status",
        headers=HO,
        json={"status": "RESPONDING"},
    )
    check("SOS OPEN->RESPONDING", r.status_code == 200)
    r = c.get(f"/api/sos/{inc}/history", headers=HO)
    check(
        "SOS history has 2 entries",
        r.status_code == 200 and len(r.json()) == 2,
    )

    # ---------- Check-In ----------
    r = c.post(
        "/api/checkins",
        headers=HV,
        json={"status": "SAFE", "broadcast_id": bid},
    )
    check("check-in SAFE", r.status_code == 201)
    r = c.post(
        "/api/checkins", headers=HV, json={"status": "OK"}
    )
    check("check-in invalid status -> 422", r.status_code == 422)
    r = c.post(
        "/api/checkins",
        headers=HV,
        json={"status": "NEED_HELP", "broadcast_id": 99999},
    )
    check("check-in bad broadcast -> 404", r.status_code == 404)
    r = c.post(
        "/api/checkins", headers=HV, json={"status": "NEED_HELP"}
    )
    check("check-in NEED_HELP (latest)", r.status_code == 201)
    r = c.get("/api/checkins/me", headers=HV)
    check(
        "my check-ins = 2",
        r.status_code == 200 and len(r.json()) == 2,
    )
    r = c.get("/api/checkins/summary", headers=HV)
    check("summary as user -> 403", r.status_code == 403)
    r = c.get("/api/checkins/summary", headers=HO)
    d = r.json()
    check(
        "summary counts latest only",
        r.status_code == 200
        and d["counts"]["NEED_HELP"] == 1
        and d["counts"]["SAFE"] == 0
        and d["checked_in_users"] == 1,
    )
    r = c.get("/api/checkins", headers=HO)
    check(
        "operator check-in list",
        r.status_code == 200 and len(r.json()) == 2,
    )

    # ---------- Audit ----------
    r = c.get("/api/audit-logs", headers=HV)
    check("audit as user -> 403", r.status_code == 403)
    r = c.get("/api/audit-logs", headers=HO)
    acts = [e["action"] for e in r.json()]
    check(
        "audit covers critical actions incl. bootstrap",
        r.status_code == 200
        and all(
            a in acts
            for a in [
                "admin_bootstrapped",
                "broadcast_created",
                "sos_created",
                "sos_status_changed",
                "checkin_created",
                "user_role_updated",
            ]
        ),
        str(acts),
    )

    # ---------- Logout ----------
    r = c.post("/api/logout", headers=HV)
    check("logout", r.status_code == 200)
    r = c.get("/api/me", headers=HV)
    check("session invalid after logout", r.status_code == 401)

print(
    f"\n=== {sum(1 for _, ok in results if ok)}/{len(results)} passed ==="
)
failed = [n for n, ok in results if not ok]
for name in failed:
    print("FAILED:", name)
sys.exit(1 if failed else 0)
