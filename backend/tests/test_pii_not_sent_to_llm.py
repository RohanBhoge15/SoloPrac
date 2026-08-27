"""Privacy tripwire: assert that NO patient PII ever reaches the external LLM.

Why this test exists
--------------------
PII stripping is wired into the synthesizer choke point, but nothing *enforces*
it. A future refactor, a new PII field on the patient schema, or a new prompt
builder could silently start leaking patient identity to NVIDIA/Groq — with no
error and no crash. That is the worst kind of regression for a medical product.

This test is the tripwire. It captures the EXACT payload that would be sent to
the LLM API (by mocking the OpenAI client) and fails loudly if a name, phone,
email, or national ID appears in it. It tests the real wiring, not strip_pii in
isolation — because the risk is the plumbing, not the helper.
"""

from __future__ import annotations

import json

import pytest

from app.services.pii import pseudonymize_id, strip_pii

# A realistic patient context carrying every kind of PII we care about.
PATIENT_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
PII_VALUES = [
    "Rohan Bhoge",  # name
    "+91-9876543210",  # phone
    "rohan@example.com",  # email
    "12 MG Road, Pune",  # address
    "1234-5678-9012",  # aadhaar
    "1996-05-15",  # date_of_birth
    PATIENT_ID,  # patient_id
]


def _patient_context() -> dict:
    return {
        "patient_context": {
            "demographics": {
                "name": "Rohan Bhoge",
                "date_of_birth": "1996-05-15",
                "age": 28,
                "gender": "M",
                "phone": "+91-9876543210",
                "email": "rohan@example.com",
                "address": "12 MG Road, Pune",
                "aadhaar": "1234-5678-9012",
                "patient_id": PATIENT_ID,
            },
            "clinical": {
                "vitals": {"bp_systolic": 140, "bp_diastolic": 90},
                "diagnoses": ["Tension headache"],
                "medications": [{"drug": "Paracetamol", "dose": "500mg"}],
            },
        },
        "citations": [{"version_number": 3, "summary": "Headache follow-up"}],
    }


class _CaptureClient:
    """Stand-in for AsyncOpenAI that records the messages it is asked to send."""

    def __init__(self):
        self.captured_messages = None

        async def _create(*, model, messages, **kwargs):
            self.captured_messages = messages

            class _Msg:
                content = '{"response": "ok"}'

            class _Choice:
                message = _Msg()

            class _Usage:
                prompt_tokens = completion_tokens = total_tokens = 0

            class _Resp:
                choices = [_Choice()]
                usage = _Usage()

            return _Resp()

        # Mirror the openai client shape: client.chat.completions.create(...)
        self.chat = type("Chat", (), {"completions": type("C", (), {"create": staticmethod(_create)})()})()


def _assert_no_pii(blob: str):
    for secret in PII_VALUES:
        assert secret not in blob, f"PII LEAKED TO LLM: {secret!r} found in payload"


# ── Unit level: the helper itself ──────────────────────────────
def test_strip_pii_removes_all_pii_keeps_clinical():
    out = strip_pii(_patient_context()["patient_context"], PATIENT_ID)
    blob = json.dumps(out)
    _assert_no_pii(blob)
    # Clinical data preserved
    assert out["clinical"]["vitals"]["bp_systolic"] == 140
    assert out["clinical"]["diagnoses"] == ["Tension headache"]
    # Pseudonym injected
    assert out["patient_ref"] == pseudonymize_id(PATIENT_ID) == "P-a1b2c3d4"


# ── Integration level: the real wiring to the LLM ──────────────
@pytest.mark.asyncio
async def test_no_pii_in_payload_sent_to_llm():
    """The payload that actually reaches the LLM API must contain no PII."""
    from app.agents.synthesizer import MaverickSynthesizer

    synth = MaverickSynthesizer()
    capture = _CaptureClient()
    synth._client = capture  # force the "NIM configured" path through our capture

    ctx = _patient_context()
    await synth.synthesize(
        query="What is the likely diagnosis?",
        context=ctx,
        patient_context=ctx["patient_context"],
        citations=ctx["citations"],
    )

    assert capture.captured_messages is not None, "LLM was never called"
    payload = json.dumps(capture.captured_messages)
    _assert_no_pii(payload)
    # Sanity: clinical content DID make it through (so we're not passing vacuously)
    assert "140" in payload or "headache" in payload.lower()


@pytest.mark.asyncio
async def test_no_pii_in_streaming_payload_sent_to_llm():
    """Same guarantee on the streaming path."""
    from app.agents.synthesizer import MaverickSynthesizer

    synth = MaverickSynthesizer()

    captured = {}

    class _EmptyStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    async def _create_stream(*, model, messages, **kwargs):
        # synthesizer does: stream = await create(...); async for chunk in stream
        captured["messages"] = messages
        return _EmptyStream()

    capture = _CaptureClient()
    capture.chat.completions.create = _create_stream
    synth._client = capture

    ctx = _patient_context()
    async for _ in synth.synthesize_stream(query="Summarize", context=ctx, patient_context=ctx["patient_context"]):
        pass

    assert "messages" in captured, "streaming LLM was never called"
    _assert_no_pii(json.dumps(captured["messages"]))
