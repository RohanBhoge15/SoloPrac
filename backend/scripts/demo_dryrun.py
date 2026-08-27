"""Pre-demo dry-run — exercises every showcase-critical flow end to end.

Covers: doctor + patient login, patient booking (creates the linked patient),
prescription/invoice/certificate PDF generation, weekly report + PDF, and the
PATIENT WEB INBOX (reports/documents land there even with no SMTP). Then the
two background flows (OCR arq job, image analysis) with bounded polling.

Run inside the backend container:
    docker compose exec backend python /app/scripts/demo_dryrun.py
"""

import asyncio
import io
import sys
from datetime import datetime, timedelta, timezone

import httpx
from PIL import Image, ImageDraw, ImageFont

BASE = "http://localhost:8000"
PASS, FAIL = "✅", "❌"
results: list[tuple[str, bool, str]] = []
total = 0
state: dict = {}


def _pdf_ok(content: bytes) -> tuple[bool, str]:
    if content[:4] == b"%PDF":
        return True, f"{len(content)}B"
    return False, f"non-PDF ({len(content)}B) starts: {content[:40]!r}"


async def _png_file() -> tuple[str, bytes]:
    # Large-ish rendered text so RapidOCR can actually read it.
    img = Image.new("RGB", (900, 300), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=44)
    except TypeError:  # older Pillow
        font = ImageFont.load_default()
    d.text((30, 40), "Patient Name: Rohan Sharma", fill="black", font=font)
    d.text((30, 120), "Diagnosis: Type 2 Diabetes", fill="black", font=font)
    d.text((30, 200), "Metformin 500mg BD", fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "rx_note.png", buf.getvalue()


async def _pdf_file() -> tuple[str, bytes]:
    img = Image.new("RGB", (400, 200), "white")
    d = ImageDraw.Draw(img)
    d.text((20, 40), "Lab Report - HbA1c 7.2%", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PDF")
    return "lab_report.pdf", buf.getvalue()


async def step(name: str, coro):
    global total
    total += 1
    try:
        detail = await coro
        results.append((name, True, detail))
        print(f"{PASS} {name}: {detail}")
    except Exception as exc:
        results.append((name, False, str(exc)[:200]))
        print(f"{FAIL} {name}: {exc}")


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=90) as doc, httpx.AsyncClient(base_url=BASE, timeout=90) as pat:
        # ── 1. Logins ──
        async def _doc_login():
            r = await doc.post("/api/v1/auth/dev-login")
            r.raise_for_status()
            if "access_token" not in doc.cookies:
                raise RuntimeError("no access_token cookie")
            me = await doc.get("/api/v1/auth/me")
            me.raise_for_status()
            state["doctor_id"] = me.json()["id"]
            return f"doctor {me.json()['email']}"

        async def _pat_login():
            r = await pat.post("/api/v1/public/auth/dev-login")
            r.raise_for_status()
            if "patient_token" not in pat.cookies:
                raise RuntimeError("no patient_token cookie")
            return "patient dev user"

        await step("doctor login", _doc_login())
        await step("patient login", _pat_login())

        # ── 2. Patient books (creates the linked Patient row) ──
        async def _book():
            did = state["doctor_id"]
            last = ""
            # Search a wide window: days 6-9, hours 9-20 — avoids seeded slots.
            for day in range(6, 10):
                for hour in range(9, 21):
                    start = (datetime.now(timezone.utc) + timedelta(days=day, hours=hour)).strftime(
                        "%Y-%m-%dT%H:%M:%S+00:00"
                    )
                    end = (datetime.now(timezone.utc) + timedelta(days=day, hours=hour, minutes=30)).strftime(
                        "%Y-%m-%dT%H:%M:%S+00:00"
                    )
                    r = await pat.post(
                        "/api/v1/patient/appointments",
                        json={"doctor_id": did, "start_at": start, "end_at": end, "reason": "dry-run"},
                    )
                    if r.status_code in (200, 201):
                        state["patient_id"] = r.json()["patient_id"]
                        return f"patient {state['patient_id'][:8]}…"
                    last = r.text[:120]
            raise RuntimeError(f"booking failed: {last}")

        await step("patient booking (creates linked patient)", _book())
        pfull = state.get("patient_id", "")

        # ── 3-6. PDF flows ──
        async def _rx():
            r = await doc.post(
                f"/api/v1/patients/{pfull}/prescriptions",
                json={
                    "diagnosis_short": "Type 2 Diabetes Mellitus",
                    "medications": [
                        {
                            "drug": "Metformin",
                            "strength": "500 mg",
                            "dose": "1 tab",
                            "frequency": "BD",
                            "duration": "30 days",
                            "instructions": "After food",
                        }
                    ],
                    "investigations": ["HbA1c"],
                    "follow_up_days": 30,
                    "follow_up_mode": "in-person",
                },
            )
            r.raise_for_status()
            rid = r.json()["id"]
            pdf = await doc.get(f"/api/v1/patients/{pfull}/prescriptions/{rid}/pdf")
            pdf.raise_for_status()
            ok, why = _pdf_ok(pdf.content)
            return f"rx pdf={why}" if ok else f"BAD PDF: {why}"

        async def _inv():
            r = await doc.post(
                f"/api/v1/patients/{pfull}/invoices",
                json={
                    "items": [{"description": "Consultation", "qty": 1, "rate": 500, "amount": 500}],
                    "tax": 18,
                    "payment_method": "upi",
                },
            )
            r.raise_for_status()
            iid = r.json()["id"]
            pdf = await doc.get(f"/api/v1/patients/{pfull}/invoices/{iid}/pdf")
            pdf.raise_for_status()
            ok, why = _pdf_ok(pdf.content)
            return f"invoice pdf={why}" if ok else f"BAD PDF: {why}"

        async def _cert():
            r = await doc.post(
                f"/api/v1/patients/{pfull}/certificates",
                json={
                    "cert_type": "fitness",
                    "patient_name": "Dry Run Patient",
                    "patient_age": 45,
                    "body": "Fit for duty",
                },
            )
            r.raise_for_status()
            cid = r.json()["id"]
            pdf = await doc.get(f"/api/v1/patients/{pfull}/certificates/{cid}/pdf")
            pdf.raise_for_status()
            ok, why = _pdf_ok(pdf.content)
            return f"cert pdf={why}" if ok else f"BAD PDF: {why}"

        async def _wreport():
            r = await doc.post(f"/api/v1/patients/{pfull}/weekly-report?layout=clinical&days=30")
            r.raise_for_status()
            pdf = await doc.get(f"/api/v1/patients/{pfull}/weekly-report/pdf?layout=clinical&days=30")
            pdf.raise_for_status()
            ok, why = _pdf_ok(pdf.content)
            return f"report pdf={why}" if ok else f"BAD PDF: {why}"

        await step("prescription + PDF", _rx())
        await step("invoice + PDF", _inv())
        await step("certificate + PDF", _cert())
        await step("weekly report + PDF", _wreport())

        # ── 7. PATIENT WEB INBOX (the key delivery path, SMTP-independent) ──
        async def _inbox():
            kinds = []
            for _ in range(10):
                r = await pat.get("/api/v1/patient/me/inbox", params={"limit": 30})
                r.raise_for_status()
                items = r.json()
                kinds = [i.get("kind") for i in items]
                if "weekly_report_ready" in kinds and "certificate_issued" in kinds:
                    return f"{len(items)} items: {sorted(set(kinds))}"
                await asyncio.sleep(1)
            raise RuntimeError(f"expected cert+report in inbox; got {sorted(set(kinds))}")

        await step("patient web inbox (booking + cert + report)", _inbox())

        # ── 8. Document OCR (async arq job, bounded) — text-bearing PNG so
        # RapidOCR (the primary OCR) can actually extract something. ──
        async def _ocr():
            name, data = await _png_file()
            r = await doc.post(
                "/api/v1/documents/parse",
                files={"file": (name, data, "image/png")},
                data={"patient_id": pfull, "sync": "false"},
            )
            r.raise_for_status()
            job_id = r.json().get("job_id") or r.json().get("id")
            for _ in range(45):
                await asyncio.sleep(2)
                jr = await doc.get(f"/api/v1/jobs/{job_id}")
                jr.raise_for_status()
                st = jr.json()
                status = st.get("status", st.get("state", ""))
                if status == "complete":
                    result = st.get("result") or {}
                    text = result.get("text") or result.get("extracted_text") or result.get("message", "")
                    return f"job {job_id[:8]}… → {str(text)[:70]}"
                if status in ("error", "failed") or (status == "complete" and not st.get("success", True)):
                    raise RuntimeError(f"job failed: {st}")
            raise RuntimeError("OCR job still running after 90s")

        await step("document OCR (arq job)", _ocr())

        # ── 9. Image analysis (background task, bounded) ──
        async def _img():
            name, data = await _png_file()
            r = await doc.post(f"/api/v1/patients/{pfull}/images", files=[("files", (name, data, "image/png"))])
            r.raise_for_status()
            for _ in range(60):
                await asyncio.sleep(2)
                pr = await doc.get(f"/api/v1/patients/{pfull}/head")
                pr.raise_for_status()
                state_jsonb = pr.json().get("state_jsonb") or {}
                summary = (state_jsonb.get("image") or {}).get("clinical_summary")
                if summary:
                    return f"analysis: {str(summary)[:60]}"
            raise RuntimeError("no image analysis after 120s")

        await step("image analysis (background)", _img())

    ok = sum(1 for _, p, _ in results if p)
    print("\n" + "=" * 60)
    print(f"DRY RUN: {ok}/{total} passed")
    failed = [(n, d) for n, p, d in results if not p]
    for n, d in failed:
        print(f"  - {n}: {d}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
