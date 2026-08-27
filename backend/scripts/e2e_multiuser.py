"""
Comprehensive CONCURRENT end-to-end harness.

Exercises every doctor-facing and patient-portal endpoint from MULTIPLE
doctors and MULTIPLE patients running SIMULTANEOUSLY (one thread per user),
then runs cross-tenant (RLS) isolation checks.

Run from host:  python backend/scripts/e2e_multiuser.py
(backend must be up at http://localhost:8000)

A 1x1 PNG and a small text file are generated in-memory for uploads.
"""

from __future__ import annotations

import base64
import datetime
import json
import sys
import threading
import time
import uuid

import requests

BASE = "http://localhost:8000/api/v1"
PW = "Demo@1234"

# tiny 1x1 png
PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
PNG = base64.b64decode(PNG_B64)
TXT = b"E2E document upload sample text.\n"

results = []
lock = threading.Lock()


def rec(name, ok, detail=""):
    with lock:
        results.append((name, bool(ok), str(detail)[:240]))


def req(
    s,
    method,
    path,
    *,
    token=None,
    json=None,
    files=None,
    data=None,
    params=None,
    expected=(200, 201, 202),
    name="",
    timeout=180,
):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = s.request(
            method, BASE + path, json=json, files=files, data=data, params=params, headers=headers, timeout=timeout
        )
    except Exception as e:
        rec(name or path, False, f"EXC {e}")
        return None
    ok = r.status_code in expected
    if not ok:
        body = r.text[:200]
        rec(name or f"{method} {path}", False, f"{r.status_code} {body}")
    else:
        rec(name or f"{method} {path}", True, f"{r.status_code}")
    return r


def agent_chat(s, token, query, patient_id=None, timeout=240):
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}
    try:
        r = s.post(
            BASE + "/agent/chat",
            json={"query": query, "patient_id": patient_id},
            headers=headers,
            stream=True,
            timeout=timeout,
        )
    except Exception as e:
        rec("agent/chat", False, f"EXC {e}")
        return "", []
    resp, cites = "", []
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        try:
            o = json.loads(line[5:].strip())
        except Exception:
            continue
        if o.get("response") is not None:
            resp, cites = o["response"], o.get("citations") or []
    rec("agent/chat", bool(resp), f"len={len(resp)} cites={len(cites)}")
    return resp, cites


# module-level capture for RLS checks
state = {"demo_token": None, "demo_pid": None, "priya_token": None, "newdoc_token": None, "newdoc_pid": None}


# ───────────────────────── DOCTOR ─────────────────────────
def doctor_run(email, pw, label, register=False):
    s = requests.Session()
    if register:
        email = f"e2e_doc_{uuid.uuid4().hex[:8]}@t.local"
        pw = "abcdef123"
        r = req(
            s,
            "post",
            "/auth/register",
            json={
                "name": label,
                "email": email,
                "password": pw,
                "phone": "9000000001",
                "clinic_name": "E2E Clinic",
                "clinic_address": "Addr",
            },
            expected=(200, 201),
            name=f"{label}: register",
        )
        # login with new creds
        r = req(
            s, "post", "/auth/login", json={"email": email, "password": pw}, expected=(200, 201), name=f"{label}: login"
        )
    else:
        r = req(
            s, "post", "/auth/login", json={"email": email, "password": pw}, expected=(200, 201), name=f"{label}: login"
        )
    if not r or r.status_code not in (200, 201):
        return
    token = (r.json() or {}).get("access_token")
    if not token:
        rec(f"{label}: no token", False)
        return

    state[label + "_token"] = token
    if label.startswith("demo"):
        state["demo_token"] = token
    if label.startswith("NewDoc"):
        state["newdoc_token"] = token

    req(s, "get", "/auth/me", token=token, name=f"{label}: GET /auth/me")
    rl = req(s, "get", "/patients?limit=100", token=token, name=f"{label}: list patients")
    patients = rl.json() if rl and rl.ok else []

    # pick an existing patient or create one
    pid = None
    if patients:
        pid = patients[0]["id"]
        pname = patients[0].get("name", "Patient")
    else:
        cr = req(
            s,
            "post",
            "/patients/manual",
            token=token,
            json={
                "name": f"E2E Walkin {uuid.uuid4().hex[:6]}",
                "dob": "1990-01-01",
                "gender": "male",
                "phone": f"911{uuid.uuid4().int % 10_000_000:07d}",
            },
            expected=(200, 201),
            name=f"{label}: create patient",
        )
        if cr and cr.ok:
            pid = cr.json()["id"]
            pname = "E2E Walkin"
            if label.startswith("NewDoc"):
                state["newdoc_pid"] = pid

    if not pid:
        rec(f"{label}: no patient to act on", False)
        return

    if label.startswith("demo"):
        state["demo_pid"] = pid

    head_r = req(s, "get", f"/patients/{pid}/head", token=token, name=f"{label}: head")
    req(s, "get", f"/patients/{pid}/timeline", token=token, name=f"{label}: timeline")
    req(s, "get", f"/patients/{pid}/at_version/1", token=token, name=f"{label}: at_version/1")
    hv0 = head_r.json().get("version_number", 1) if head_r and head_r.ok else 1
    if hv0 >= 2:
        req(s, "get", f"/patients/{pid}/diff?v1=1&v2={hv0}", token=token, name=f"{label}: diff")

    # legacy PATCH fields (still supported) -> new version
    head_r = req(s, "get", f"/patients/{pid}/head", token=token)
    hv = head_r.json().get("version_number", 1) if head_r and head_r.ok else 1
    req(
        s,
        "patch",
        f"/patients/{pid}/fields?expected_version={hv}",
        token=token,
        json={"blood_group": "O+", "allergies": "None"},
        name=f"{label}: PATCH fields",
    )

    # ── NEW: status-note version (the redesigned New Version) ──
    head_r2 = req(s, "get", f"/patients/{pid}/head", token=token)
    hv2 = head_r2.json().get("version_number", 1) if head_r2 and head_r2.ok else 1
    note = f"E2E status note {uuid.uuid4().hex[:8]}: patient stable, follow up in 2 weeks."
    nr = req(
        s,
        "post",
        f"/patients/{pid}/versions/note",
        token=token,
        json={"note": note},
        expected=(200, 201),
        name=f"{label}: POST versions/note",
    )
    note_vn = None
    if nr and nr.ok:
        note_vn = (nr.json() or {}).get("version_number")
        if note_vn != hv2 + 1:
            rec(f"{label}: note version number", False, f"expected {hv2 + 1} got {note_vn}")
        else:
            rec(f"{label}: note version number", True, f"v{note_vn}")
        # verify summary + state carry the note
        nv = nr.json() or {}
        if (nv.get("summary") or "") != note:
            rec(f"{label}: note summary", False, nv.get("summary"))
        else:
            rec(f"{label}: note summary", True)
        sj = nv.get("state_jsonb", {})
        if sj.get("status_note") != note or "status_notes" not in sj:
            rec(f"{label}: note in state_jsonb", False, "missing status_note/status_notes")
        else:
            rec(f"{label}: note in state_jsonb", True)

    # prescription create + approve -> version
    rx = {
        "diagnosis_short": "E2E viral fever",
        "medications": [
            {
                "drug": "Paracetamol",
                "strength": "500mg",
                "dose": "1 tab",
                "frequency": "TDS",
                "route": "PO",
                "duration": "3 days",
            }
        ],
        "instructions": "Rest",
        "follow_up_days": 3,
        "follow_up_mode": "in-person",
    }
    pr = req(
        s,
        "post",
        f"/patients/{pid}/prescriptions",
        token=token,
        json=rx,
        expected=(200, 201),
        name=f"{label}: create prescription",
    )
    if pr and pr.ok:
        rx_id = (pr.json() or {}).get("id")
        if rx_id:
            req(
                s,
                "post",
                f"/prescriptions/{rx_id}/approve",
                token=token,
                expected=(200, 201),
                name=f"{label}: approve prescription",
            )

    # invoice + certificate
    req(
        s,
        "post",
        f"/patients/{pid}/invoices",
        token=token,
        json={"consultation_fee": 400, "medicine_cost": 0, "payment_method": "cash", "notes": "E2E"},
        expected=(200, 201),
        name=f"{label}: create invoice",
    )
    req(
        s,
        "post",
        f"/patients/{pid}/certificates",
        token=token,
        json={"cert_type": "sick_leave", "cert_jsonb": {"diagnosis": "E2E fever", "duration_days": 3}},
        expected=(200, 201),
        name=f"{label}: create certificate",
    )

    # document parse + save-to-patient
    dr = req(
        s,
        "post",
        "/documents/parse",
        token=token,
        files={"file": ("e2e.png", PNG, "image/png")},
        expected=(200, 201, 207, 422),
        name=f"{label}: document parse",
    )
    if dr and dr.ok and dr.status_code in (200, 201):
        drj = dr.json() or {}
        doc_id = drj.get("id") or drj.get("doc_id")
        if doc_id:
            req(
                s,
                "post",
                f"/documents/{doc_id}/save-to-patient",
                token=token,
                json={"patient_id": pid},
                expected=(200, 201),
                name=f"{label}: doc save-to-patient",
            )

    # images upload x2 + compare + save-to-record
    iu = req(
        s,
        "post",
        f"/patients/{pid}/images",
        token=token,
        files={"files": [("a.png", PNG, "image/png"), ("b.png", PNG, "image/png")]},
        expected=(200, 201),
        name=f"{label}: image upload",
    )
    paths = []
    if iu and iu.ok:
        ij = iu.json() or {}
        items = ij if isinstance(ij, list) else ij.get("results") or ([ij] if ij else [])
        for it in items:
            if isinstance(it, dict):
                p = it.get("file_path") or it.get("path") or it.get("s3_key")
                if p:
                    paths.append(p)
    if len(paths) >= 2:
        cmp = req(
            s,
            "post",
            f"/patients/{pid}/images/compare",
            token=token,
            json={"image_paths": paths[:2]},
            expected=(200, 201),
            name=f"{label}: image compare",
        )
        cid = (cmp.json() or {}).get("comparison_id") if cmp and cmp.ok else None
        if cid:
            req(
                s,
                "post",
                f"/patients/{pid}/images/comparisons/{cid}/save-to-record",
                token=token,
                expected=(200, 201),
                name=f"{label}: compare save",
            )

    # calendar
    req(s, "get", "/calendar/working-hours", token=token, name=f"{label}: working-hours")
    now = datetime.datetime.now(datetime.timezone.utc).date()
    d2 = (now + datetime.timedelta(days=5)).isoformat()
    req(
        s,
        "get",
        f"/calendar/slots?date_from={now.isoformat()}&date_to={d2}&duration=20",
        token=token,
        name=f"{label}: slots",
    )
    _h = uuid.uuid4().int
    sh = 6 + (_h % 18)
    sm = (_h // 18) % 60
    start = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=9)).replace(
        hour=sh, minute=sm, second=0
    )
    end = start + datetime.timedelta(minutes=20)
    req(
        s,
        "post",
        "/calendar/appointments",
        token=token,
        json={
            "patient_id": pid,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "reason": "E2E follow-up",
            "source": "manual",
        },
        expected=(200, 201),
        name=f"{label}: create appointment",
    )

    # weekly report
    req(
        s,
        "post",
        f"/patients/{pid}/weekly-report",
        token=token,
        json={},
        expected=(200, 201),
        name=f"{label}: weekly-report gen",
    )
    req(
        s,
        "post",
        f"/weekly-report/{pid}/ai-summary",
        token=token,
        json={},
        expected=(200, 201),
        name=f"{label}: weekly-report ai-summary",
    )
    req(s, "get", f"/patients/{pid}/weekly-report/pdf", token=token, name=f"{label}: weekly-report pdf")

    # misc
    req(s, "get", "/risk-alerts", token=token, name=f"{label}: risk-alerts")
    req(s, "get", "/security/rate-limits", token=token, name=f"{label}: rate-limits")
    req(s, "get", "/security/upload-status", token=token, name=f"{label}: upload-status")
    req(s, "get", "/agent/health", token=token, name=f"{label}: agent health")
    req(s, "get", "/agent/rate-limit", token=token, name=f"{label}: agent rate-limit")
    req(s, "get", "/auth/sessions", token=token, name=f"{label}: sessions")
    req(s, "get", "/auth/me/data", token=token, name=f"{label}: me/data")

    # agent chat (SSE) — verify grounding on the note version
    if note_vn:
        resp, cites = agent_chat(
            s, token, f"Summarize {pname}'s record and mention the latest status note.", patient_id=pid
        )
        if not any(c.get("version_number") == note_vn for c in cites):
            rec(f"{label}: note cited in chat", False, f"cites={[c.get('version_number') for c in cites]}")
        else:
            rec(f"{label}: note cited in chat", True, f"v{note_vn}")


# ───────────────────────── PATIENT ─────────────────────────
def patient_run(email, pw, label, register=False, doctor_id=None):
    s = requests.Session()
    if register:
        email = f"e2e_pat_{uuid.uuid4().hex[:8]}@t.local"
        pw = "abcdef123"
        req(
            s,
            "post",
            "/public/auth/register",
            json={
                "name": label,
                "email": email,
                "password": pw,
                "phone": "9800000001",
                "dob": "1992-05-05",
                "gender": "female",
                "address": "E2E Patient Address",
            },
            expected=(200, 201),
            name=f"{label}: register",
        )
        r = req(
            s,
            "post",
            "/public/auth/login",
            json={"email": email, "password": pw},
            expected=(200, 201),
            name=f"{label}: login",
        )
    else:
        r = req(
            s,
            "post",
            "/public/auth/login",
            json={"email": email, "password": pw},
            expected=(200, 201),
            name=f"{label}: login",
        )
    if not r or r.status_code not in (200, 201):
        return

    req(s, "get", "/patient/me/profile", name=f"{label}: GET profile")
    req(
        s,
        "put",
        "/patient/me/profile",
        json={"blood_group": "B+", "allergies": "None", "height_cm": 165, "weight_kg": 60},
        name=f"{label}: PUT profile",
    )

    ds = req(s, "get", "/public/doctors/search?q=", name=f"{label}: doctor search")
    docs = (ds.json() or {}).get("doctors", []) if ds and ds.ok else []
    did = doctor_id or (docs[0]["id"] if docs else None)

    if did:
        req(s, "get", f"/public/doctors/{did}", name=f"{label}: doctor detail")
        h = uuid.uuid4().int
        bh = 8 + (h % 10)
        bm = (h // 10) % 60
        start = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3)).replace(
            hour=bh, minute=bm, second=0
        )
        end = start + datetime.timedelta(minutes=20)
        req(
            s,
            "post",
            "/patient/appointments",
            json={"doctor_id": did, "start_at": start.isoformat(), "end_at": end.isoformat(), "reason": "E2E consult"},
            expected=(200, 201),
            name=f"{label}: book appointment",
        )
    else:
        rec(f"{label}: no doctor to book", False)

    req(s, "get", "/patient/me/appointments", name=f"{label}: my appointments")
    ib = req(s, "get", "/patient/me/inbox", name=f"{label}: inbox")
    if ib and ib.ok and isinstance(ib.json(), list) and ib.json():
        nid = ib.json()[0].get("id")
        if nid:
            req(s, "patch", f"/patient/me/inbox/{nid}/read", name=f"{label}: mark read")
    req(s, "get", "/patient/me/reports", name=f"{label}: reports")
    req(s, "post", "/public/auth/logout", name=f"{label}: logout")


# ───────────────────────── RLS checks ─────────────────────────
def rls_checks():
    # Doctor B cannot read Doctor A's patient
    if state["demo_token"] and state["demo_pid"] and state["priya_token"]:
        s = requests.Session()
        r = s.get(BASE + f"/patients/{state['demo_pid']}", headers={"Authorization": f"Bearer {state['priya_token']}"})
        ok = r.status_code in (403, 404)
        rec("RLS: DoctorB reads DoctorA patient -> 403/404", ok, f"{r.status_code}")
        r2 = s.get(
            BASE + f"/patients/{state['demo_pid']}/head", headers={"Authorization": f"Bearer {state['priya_token']}"}
        )
        rec("RLS: DoctorB reads DoctorA head -> 403/404", r2.status_code in (403, 404), f"{r2.status_code}")
    else:
        rec("RLS: setup incomplete", False)

    # Anonymous cannot read
    if state["demo_pid"]:
        s = requests.Session()
        r = s.get(BASE + f"/patients/{state['demo_pid']}")
        rec("RLS: anonymous read -> 401", r.status_code == 401, f"{r.status_code}")

    # New doc's patient not visible to demo doc
    if state["newdoc_token"] and state["newdoc_pid"] and state["demo_token"]:
        s = requests.Session()
        r = s.get(BASE + f"/patients/{state['newdoc_pid']}", headers={"Authorization": f"Bearer {state['demo_token']}"})
        rec("RLS: demo reads newdoc patient -> 403/404", r.status_code in (403, 404), f"{r.status_code}")


def main():
    t0 = time.time()
    threads = []
    docs = [
        ("demo@soloprac.dev", PW, "demo"),
        ("priya@soloprac.dev", PW, "priya"),
        (None, None, "NewDoc(e2e)"),
    ]
    pats = [
        ("arjun@demo.dev", PW, "Arjun"),
        ("sneha@demo.dev", PW, "Sneha"),
        ("raj@demo.dev", PW, "Raj"),
        (None, None, "NewPat(e2e)"),
    ]

    # pre-fetch a doctor id for patient booking (demo doctor)
    demo_id = None
    try:
        rs = requests.Session()
        lr = rs.post(BASE + "/public/auth/login", json={"email": "demo@soloprac.dev", "password": PW})
        # patient login above uses patient portal; we need a DOCTOR id via public search
        sr = rs.get(BASE + "/public/doctors/search?q=Dev")
        docs_list = (sr.json() or {}).get("doctors", []) if sr.ok else []
        demo_id = docs_list[0]["id"] if docs_list else None
    except Exception:
        demo_id = None

    for email, pw, label in docs:
        t = threading.Thread(target=doctor_run, args=(email, pw, label, email is None), name=label)
        threads.append(t)
    for email, pw, label in pats:
        t = threading.Thread(target=patient_run, args=(email, pw, label, email is None, demo_id), name=label)
        threads.append(t)

    print(f"Launching {len(threads)} concurrent user sessions...")
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("Running RLS isolation checks...")
    rls_checks()

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n============ E2E RESULTS ============\n{passed}/{total} passed in {time.time() - t0:.1f}s\n")
    fails = [(n, d) for n, ok, d in results if not ok]
    for n, d in fails:
        print(f"  FAIL: {n} — {d}")
    if not fails:
        print("ALL GREEN")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
