"""Walk-in ↔ User auto-linking with disambiguation.

Two-tier matching to avoid the shared-phone problem (family handset, elderly
parent, employer's number). Never asks the doctor to confirm anything — the
patient does the final tie-break themselves via a pending-matches list.

Rules:
  * STRONG match  → set Patient.user_id automatically. Match requires:
      phone matches AND (dob matches OR name similarity >= NAME_SIMILARITY_STRONG)
  * WEAK match    → phone-only. Do NOT link. Surface as a pending match so
                    the user can claim/reject in-app.

Same helper is called from both directions:
  * Patient signup → scan unlinked walk-ins for candidates.
  * Doctor creates walk-in → scan existing Users for candidates.

Idempotent: skip if user_id already set, skip if user is already in the
patient's link_rejected_by_user_ids list.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Patient, User
from app.services.encryption import decrypt_value
from app.utils.phone import normalize_phone, phones_match

logger = logging.getLogger(__name__)


def _tokens(name: Optional[str]) -> list[str]:
    """Split a name into lowercase alphabetic tokens (drop punctuation/dots)."""
    if not name:
        return []
    return [t for t in re.split(r"[^a-zA-Z]+", name.lower()) if t]


def _names_compatible(a: Optional[str], b: Optional[str]) -> bool:
    """True iff two names could plausibly refer to the same person.

    Uses token-prefix matching, which is the right model for Indian names:
      "Priya S."       ~ "Priya Sharma"  → tokens {priya, s} ⊑ {priya, sharma}
      "P. Sharma"      ~ "Priya Sharma"  → {p, sharma} ⊑ {priya, sharma}
      "Amit"           ~ "Amit Kumar"    → {amit} ⊑ {amit, kumar}
      "Priya Sharma"   ≁ "Rajesh Sharma" → {rajesh, sharma} ⊄ {priya, sharma}
      "Sunita"         ≁ "Amit Kumar"    → no token matches

    Rule: EVERY token in the shorter name must be a prefix of SOME token in
    the longer name (or vice-versa if same length). This catches abbreviations
    in both directions while rejecting different first names that share a
    common surname.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    # Each short-side token must find a long-side token it prefixes (or is
    # prefixed by — abbreviations run both ways: "P." vs "Priya" and "Amit"
    # vs "Amit K.").
    used: set[int] = set()
    for s in short:
        matched = False
        for i, l in enumerate(long_):
            if i in used:
                continue
            if l.startswith(s) or s.startswith(l):
                used.add(i)
                matched = True
                break
        if not matched:
            return False
    return True


@dataclass
class MatchResult:
    patient: Patient
    plaintext_phone: str  # decrypted phone from Patient.phone_enc
    strong: bool  # True iff we should auto-link this row


def _walkin_demographics(patient: Patient) -> dict:
    """Best-effort extract of the walk-in's demographics from its head version."""
    try:
        state = getattr(patient.head_version, "state_jsonb", None) or {}
        demo = state.get("demographics") or {}
        return demo if isinstance(demo, dict) else {}
    except Exception:
        return {}


def _dob_matches(walkin_demo: dict, user: User) -> bool:
    """Compare stored patient dob (ISO string) to user.dob (datetime/date)."""
    demo_dob = walkin_demo.get("dob")
    if not demo_dob or not user.dob:
        return False
    try:
        # user.dob is a date/datetime; demo_dob is "YYYY-MM-DD..." string
        return str(user.dob).startswith(str(demo_dob)[:10]) or str(demo_dob).startswith(str(user.dob)[:10])
    except Exception:
        return False


def _classify_match(walkin_demo: dict, user: User) -> Tuple[bool, str]:
    """Return (is_strong, reason). Assumes phone already matched.

    Strong link requires phone + one of:
      - matching DOB (definitive)
      - compatible name tokens (handles abbreviations / short-forms)

    Falls back to weak (phone-only) so the patient disambiguates in-app.
    """
    if _dob_matches(walkin_demo, user):
        return True, "phone+dob"
    demo_name = walkin_demo.get("name")
    if _names_compatible(demo_name, user.name):
        return True, f"phone+name({demo_name!r} ~ {user.name!r})"
    return False, f"phone-only ({demo_name!r} vs {user.name!r})"


async def find_candidates_for_user(db: AsyncSession, user: User) -> List[MatchResult]:
    """Return every unlinked walk-in Patient whose phone matches this user.

    Includes both strong AND weak matches — caller decides what to do with each.
    Filters out patients where this user has already clicked "Not me".
    """
    if not user.phone:
        return []
    norm = normalize_phone(user.phone)
    if len(norm) != 10:
        return []

    result = await db.execute(select(Patient).where(Patient.user_id.is_(None)))
    candidates = result.scalars().all()

    out: List[MatchResult] = []
    for p in candidates:
        # Skip if this user already rejected this walk-in
        rejected = p.link_rejected_by_user_ids or []
        if user.id in rejected:
            continue
        if not p.phone_enc:
            continue
        try:
            plaintext = await decrypt_value(db, p.phone_enc, "patient-phone")
        except Exception as exc:
            logger.debug("phone decrypt failed for patient %s: %s", p.id, exc)
            continue
        if not phones_match(plaintext, user.phone):
            continue

        demo = _walkin_demographics(p)
        strong, reason = _classify_match(demo, user)
        logger.debug("Match found: patient=%s user=%s strong=%s reason=%s", p.id, user.id, strong, reason)
        out.append(MatchResult(patient=p, plaintext_phone=plaintext, strong=strong))
    return out


async def strong_link_walkins_to_user(db: AsyncSession, user: User) -> int:
    """Auto-link every STRONG match. Weak matches are left for the pending list.

    Returns the number of walk-ins linked.
    """
    matches = await find_candidates_for_user(db, user)
    linked = 0
    for m in matches:
        if not m.strong:
            continue
        m.patient.user_id = user.id
        linked += 1
        logger.info("Strong-linked walk-in %s to user %s", m.patient.id, user.id)
    if linked:
        await db.flush()
    return linked


async def find_user_for_walkin(db: AsyncSession, walkin_phone: str, walkin_demo: dict) -> Tuple[Optional[User], bool]:
    """Reverse direction: doctor creates walk-in, look for an existing User.

    Returns (user, is_strong). If is_strong is False the caller should NOT set
    Patient.user_id — instead let the user claim it later from their portal.
    """
    if not walkin_phone:
        return None, False
    norm = normalize_phone(walkin_phone)
    if len(norm) != 10:
        return None, False

    u_res = await db.execute(select(User))
    for u in u_res.scalars().all():
        if not u.phone:
            continue
        if not phones_match(u.phone, walkin_phone):
            continue
        strong, reason = _classify_match(walkin_demo, u)
        logger.debug("Reverse match user=%s strong=%s reason=%s", u.id, strong, reason)
        return u, strong
    return None, False
