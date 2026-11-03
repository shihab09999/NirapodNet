"""NirapodNet automated checks (Phase 3 security).

Run from the repository root with the project dependencies plus
httpx and websockets installed:

    pip install -r requirements.txt httpx websockets
    python tests/run_phase3_checks.py

The script uses a temporary database, a deterministic signing
key and a bootstrap admin, so it never touches a real
nirapodnet.db. It exits with code 0 only when every check
passes. Phase 2 regression is covered separately by
tests/run_phase2_checks.py.
"""

import hashlib
import os
import sqlite3
import sys
import tempfile
import time

_tmpdir = tempfile.mkdtemp(prefix="nirapodnet-phase3-")
_db_path = os.path.join(_tmpdir, "test.db")
os.environ["NIRAPODNET_DB"] = "sqlite:///" + _db_path
os.environ["NIRAPODNET_ADMIN_USERNAME"] = "bossadmin"
os.environ["NIRAPODNET_ADMIN_PASSWORD"] = "adminpass123"
os.environ["NIRAPODNET_SIGNING_KEY"] = "phase3-test-signing-key"
os.environ["NIRAPODNET_LOGIN_RATE_LIMIT"] = "10"

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


def login(c, username, password="password123"):
    r = c.post(
        "/api/login",
        json={"username": username, "password": password},
    )
    return r


def stored_session_tokens():
    con = sqlite3.connect(_db_path)
    try:
        rows = con.execute("SELECT token FROM sessions").fetchall()
        return [row[0] for row in rows]
    finally:
        con.close()


with TestClient(app, raise_server_exceptions=False) as c:
    # ---------- Security headers ----------
    r = c.get("/api")
    check("P3 /api online", r.status_code == 200)
    check(
        "P3 security headers on /api",
        r.headers.get("X-Content-Type-Options") == "nosniff"
        and r.headers.get("X-Frame-Options") == "DENY"
        and "script-src 'self'" in r.headers.get(
            "Content-Security-Policy", ""
        )
        and r.headers.get("Referrer-Policy") == "no-referrer",
        str(dict(r.headers)),
    )
    check(
        "P3 no HSTS over plain HTTP",
        "Strict-Transport-Security" not in r.headers,
    )

    # ---------- Users ----------
    for username in ("victim", "operator1", "capuser", "roleuser",
                     "ratelimituser"):
        r = c.post(
            "/api/register",
            json={"username": username, "password": "password123"},
        )
        check(f"P3 register {username}", r.status_code == 201)

    r = login(c, "bossadmin", "adminpass123")
    check("P3 bootstrap admin login", r.status_code == 200)
    HA = {"Authorization": f"Bearer {r.json()['token']}"}

    r = c.post(
        "/api/login",
        json={"username": "victim", "password": "password123"},
    )
    check("P3 victim login", r.status_code == 200)
    vt = r.json()["token"]
    HV = {"Authorization": f"Bearer {vt}"}

    # ---------- Session token hashing ----------
    stored = stored_session_tokens()
    check(
        "P3 session token stored hashed, not plain",
        vt not in stored
        and hashlib.sha256(vt.encode()).hexdigest() in stored,
    )

    # ---------- Operator ----------
    r = c.get("/api/admin/users", headers=HA)
    users = {u["username"]: u["id"] for u in r.json()}
    r = c.patch(
        f"/api/admin/users/{users['operator1']}/role",
        headers=HA,
        json={"role": "operator"},
    )
    check("P3 promote operator", r.status_code == 200)
    r = login(c, "operator1")
    HO = {"Authorization": f"Bearer {r.json()['token']}"}
    check("P3 operator login", r.status_code == 200)

    # ---------- Broadcast signing ----------
    r = c.post(
        "/api/broadcasts",
        headers=HO,
        json={
            "type": "Flood Warning",
            "message": "Move to shelter",
            "priority": "critical",
        },
    )
    check(
        "P3 broadcast has signature",
        r.status_code == 201
        and isinstance(r.json().get("signature"), str)
        and len(r.json()["signature"]) == 64,
        str(r.json()),
    )
    bid = r.json()["id"]
    r = c.get(f"/api/broadcasts/{bid}/verify", headers=HV)
    check(
        "P3 broadcast verify valid",
        r.status_code == 200
        and r.json().get("valid") is True
        and r.json().get("signature_present") is True,
        str(r.json()),
    )

    # Tamper with the stored broadcast directly: verification
    # must then fail. This is the tamper-evidence check.
    con = sqlite3.connect(_db_path)
    con.execute(
        "UPDATE broadcasts SET message = ? WHERE id = ?",
        ("Tampered message", bid),
    )
    con.commit()
    con.close()
    r = c.get(f"/api/broadcasts/{bid}/verify", headers=HV)
    check(
        "P3 tampered broadcast verify invalid",
        r.status_code == 200 and r.json().get("valid") is False,
        str(r.json()),
    )

    # ---------- Idempotency: SOS ----------
    r = c.get("/api/sos", headers=HO)
    sos_before = len(r.json())
    key = {"Idempotency-Key": "sos-phase3-1"}
    r1 = c.post(
        "/api/sos",
        headers={**HV, **key},
        json={"emergency_type": "flood", "latitude": 23.7,
              "longitude": 90.4, "description": "help"},
    )
    r2 = c.post(
        "/api/sos",
        headers={**HV, **key},
        json={"emergency_type": "flood", "latitude": 23.7,
              "longitude": 90.4, "description": "help"},
    )
    r = c.get("/api/sos", headers=HO)
    check(
        "P3 SOS idempotency: same incident, one row",
        r1.status_code == 201 and r2.status_code == 201
        and r1.json()["incident_id"] == r2.json()["incident_id"]
        and len(r.json()) == sos_before + 1,
        f"{r1.json()} {r2.json()} count={len(r.json())}",
    )

    # ---------- Idempotency: broadcast ----------
    key = {"Idempotency-Key": "bc-phase3-1"}
    r1 = c.post(
        "/api/broadcasts",
        headers={**HO, **key},
        json={"type": "T", "message": "idem", "priority": "high"},
    )
    r2 = c.post(
        "/api/broadcasts",
        headers={**HO, **key},
        json={"type": "T", "message": "idem", "priority": "high"},
    )
    check(
        "P3 broadcast idempotency: same id",
        r1.status_code == 201 and r2.status_code == 201
        and r1.json()["id"] == r2.json()["id"]
        and r1.json()["signature"] == r2.json()["signature"],
    )

    # ---------- Idempotency: check-in and message ----------
    r = c.get("/api/checkins/me", headers=HV)
    ci_before = len(r.json())
    key = {"Idempotency-Key": "ci-phase3-1"}
    r1 = c.post(
        "/api/checkins", headers={**HV, **key},
        json={"status": "SAFE"},
    )
    r2 = c.post(
        "/api/checkins", headers={**HV, **key},
        json={"status": "SAFE"},
    )
    r = c.get("/api/checkins/me", headers=HV)
    check(
        "P3 check-in idempotency: one row",
        r1.status_code == 201 and r2.status_code == 201
        and r1.json()["id"] == r2.json()["id"]
        and len(r.json()) == ci_before + 1,
    )

    key = {"Idempotency-Key": "msg-phase3-1"}
    r1 = c.post(
        "/messages", headers={**HV, **key},
        json={"client_id": "m-idem-1", "sender_id": 999,
              "content": "idem message"},
    )
    r2 = c.post(
        "/messages", headers={**HV, **key},
        json={"client_id": "m-idem-2", "sender_id": 999,
              "content": "different body, same key"},
    )
    check(
        "P3 message idempotency: original returned",
        r1.status_code == 200 and r2.status_code == 200
        and r1.json()["id"] == r2.json()["id"],
    )

    # ---------- Input validation ----------
    r = c.post(
        "/messages", headers=HV,
        json={"client_id": "bad-1", "sender_id": 999,
              "content": "bad\x00content"},
    )
    check("P3 NUL in message -> 422", r.status_code == 422)
    r = c.post(
        "/api/broadcasts", headers=HO,
        json={"type": "T", "message": "bad\x01msg",
              "priority": "high"},
    )
    check("P3 control char in broadcast -> 422", r.status_code == 422)
    r = c.post(
        "/api/register",
        json={"username": "bad user", "password": "password123"},
    )
    check("P3 username with space -> 422", r.status_code == 422)

    # ---------- Session cap ----------
    cap_tokens = []
    for _ in range(6):
        r = login(c, "capuser")
        cap_tokens.append(r.json()["token"])
    r = c.get(
        "/api/me",
        headers={"Authorization": f"Bearer {cap_tokens[0]}"},
    )
    first_dead = r.status_code == 401
    r = c.get(
        "/api/me",
        headers={"Authorization": f"Bearer {cap_tokens[-1]}"},
    )
    last_alive = r.status_code == 200
    check(
        "P3 session cap: oldest dropped, newest works",
        first_dead and last_alive,
    )

    # ---------- Role change invalidates sessions ----------
    r = login(c, "roleuser")
    role_token = r.json()["token"]
    HRU = {"Authorization": f"Bearer {role_token}"}
    r = c.get("/api/me", headers=HRU)
    check("P3 roleuser session works before change",
          r.status_code == 200)
    r = c.patch(
        f"/api/admin/users/{users['roleuser']}/role",
        headers=HA,
        json={"role": "operator"},
    )
    check("P3 roleuser promoted", r.status_code == 200)
    r = c.get("/api/me", headers=HRU)
    check(
        "P3 old session invalid after role change",
        r.status_code == 401,
    )
    r = login(c, "roleuser")
    check(
        "P3 re-login after role change, new role",
        r.status_code == 200
        and r.json()["user"]["role"] == "operator",
    )

    # ---------- Login rate limit ----------
    codes = []
    for _ in range(11):
        r = c.post(
            "/api/login",
            json={"username": "ratelimituser",
                  "password": "wrongpass1"},
        )
        codes.append(r.status_code)
    check(
        "P3 login rate limit: 10 allowed, 11th 429",
        codes[:10] == [401] * 10 and codes[10] == 429,
        str(codes),
    )

    # ---------- WebSocket replay + rate limit ----------
    try:
        with c.websocket_connect(f"/ws?token={vt}") as ws:
            now = int(time.time())
            ws.send_json({
                "client_id": "ws-seq-1", "content": "seq hi",
                "seq": 1, "ts": now,
            })
            ack = ws.receive_json()
            check("P3 WS seq 1 ack", ack.get("type") == "ack")
            ws.send_json({
                "client_id": "ws-seq-2", "content": "replay",
                "seq": 1, "ts": now,
            })
            err = ws.receive_json()
            check(
                "P3 WS replayed seq -> error",
                err.get("type") == "error",
            )
            ws.send_json({
                "client_id": "ws-seq-3", "content": "stale",
                "seq": 2, "ts": now - 1000,
            })
            err = ws.receive_json()
            check(
                "P3 WS stale timestamp -> error",
                err.get("type") == "error",
            )
            ws.send_json({
                "client_id": "ws-seq-4", "content": "ok again",
                "seq": 3, "ts": now,
            })
            ack = ws.receive_json()
            check("P3 WS seq 3 ack", ack.get("type") == "ack")
    except Exception as exc:  # noqa: BLE001
        check("P3 WS replay flow", False, repr(exc))

    try:
        with c.websocket_connect(f"/ws?token={vt}") as ws:
            frames = []
            for i in range(31):
                ws.send_json({
                    "client_id": f"ws-rate-{i}",
                    "content": "rate test",
                })
                frames.append(ws.receive_json())
            check(
                "P3 WS rate limit: 30 ack, 31st error",
                all(f.get("type") == "ack" for f in frames[:30])
                and frames[30].get("type") == "error",
                str([f.get("type") for f in frames]),
            )
    except Exception as exc:  # noqa: BLE001
        check("P3 WS rate limit flow", False, repr(exc))

print(
    f"\n=== {sum(1 for _, ok in results if ok)}/{len(results)} passed ==="
)
failed = [n for n, ok in results if not ok]
for name in failed:
    print("FAILED:", name)
sys.exit(1 if failed else 0)
