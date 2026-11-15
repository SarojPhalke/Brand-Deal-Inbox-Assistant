"""Next step, reply points and draft replies. Nothing is ever sent.

Split of work:
  code -> decides the next step and writes the facts/points a reply must contain
  LLM  -> only rephrases those points into a natural email (optional)
  code -> checks the LLM draft; if it breaks a rule we fall back to a template
"""
import json
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from src.rules import _norm_product, inr, missing_fields

HINGLISH_WORDS = {"namaste", "hum", "aap", "aapke", "aapko", "kya", "hai", "hain", "karna",
                  "chahte", "dhanyavaad", "shukriya", "ji", "saath", "ek", "ka"}
MAX_WORDS = 140
URL_RE = re.compile(r"https?://|www\.", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

OPENING = {
    "accept": "Thank you for the offer.",
    "negotiate": "Thanks for reaching out. I'm interested and would like to align on a few terms.",
    "ask_for_details": "Thanks for reaching out.",
    "decline": "Thank you for thinking of me.",
}

DRAFT_SYSTEM = """You draft short email replies for a creator. The creator reviews every draft; nothing is sent automatically.
Rules:
- Use ONLY the facts and points in the JSON. Do not invent amounts, dates, deliverables or commitments.
- Keep the meaning of every point and every number exactly as given.
- 3 to 6 sentences, under 100 words, polite and professional, first person ("I").
- Never include phone numbers, addresses, links or email addresses.
- Write in the requested language: english, hinglish (Hindi in Roman script mixed with English) or hindi.
- Output JSON only: {"draft": "<the full email, greeting and sign-off included>"}"""


@dataclass
class Recommendation:
    next_step: str
    points: list = field(default_factory=list)   # first-person sentences the reply must contain
    draft: Optional[str] = None
    draft_source: Optional[str] = None           # "llm" | "template" | None
    language: str = "english"
    draft_problems: list = field(default_factory=list)  # why an LLM draft was rejected


# ---------- small helpers ----------
def safe_text(s: Optional[str], maxlen: int = 40) -> str:
    """Names/brands come from untrusted email text. Keep only plain characters, capped."""
    s = re.sub(r"[^A-Za-z0-9 &.'-]", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()[:maxlen]


def detect_language(text: str) -> str:
    if re.search(r"[\u0900-\u097F]", text or ""):
        return "hindi"
    tokens = re.findall(r"[a-z]+", (text or "").lower())
    return "hinglish" if sum(t in HINGLISH_WORDS for t in tokens) >= 3 else "english"


def _join(items: list) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _exclusivity(profile: dict, product: Optional[str]):
    p = _norm_product(product)
    for ex in profile["current_exclusivity"]:
        c = _norm_product(ex["category"])
        if p and c and (p in c or c in p):
            return ex["category"], ex["until"]
    return None, None


# ---------- decisions (pure code) ----------
def decide_next_step(category: str, codes: set) -> str:
    if category == "spam":
        return "ignore"
    if category == "scam_or_phishing":
        return "report"
    if category == "not_a_fit":
        return "decline"
    if category == "needs_more_info":
        return "ask_for_details"
    if codes & {"below_rate", "unusual_usage_rights", "gifting_only", "terms_worsened"}:
        return "negotiate"
    if codes & {"agency_unverified", "sender_changed"}:
        return "ask_for_details"
    return "accept"


def reply_points(step: str, g, profile: dict) -> list:
    a, m = g.assessment, g.merged
    flags = {f.code: f for f in a.flags}
    brand = safe_text(m.brand) or "your brand"
    pts = []

    if step == "decline":
        if "exclusivity_conflict" in flags:
            cat, until = _exclusivity(profile, m.category_of_product)
            pts.append(f"I currently have an exclusivity commitment in the {cat} category until {until}, so I can't take this on.")
        if "content_rule_violation" in flags:
            pts.append("I don't promote gambling, betting, fantasy-sports or crypto products, so I'll have to pass.")

    elif step == "negotiate":
        rate = a.rate_card_inr
        if "gifting_only" in flags:
            pts.append((f"I don't take product-only deals for this scope; my rate is {inr(rate)}, and I'm happy to discuss a paid fee."
                        if rate else "I don't take product-only deals for this scope, but I'm happy to discuss a paid fee."))
        elif "below_rate" in flags and rate:
            pts.append(f"For this scope my rate is {inr(rate)}, so I'd need the fee at that level.")
        if "unusual_usage_rights" in flags:
            pts.append("My rate includes up to 3 months of paid-ad usage; longer, perpetual or whitelisting usage is priced separately, so please tell me the usage you need.")

    elif step == "ask_for_details":
        if "deadline_passed" in flags:
            pts.append(f"The deadline you mentioned ({m.deadline}) has already passed. Is that a typo, or has it been extended?")
        labels = {"deliverables": "the deliverables you need (platform and number of posts)",
                  "compensation": "your budget", "timeline": "the timeline or go-live date"}
        wanted = [labels[x] for x in missing_fields(m)]
        if m.usage_rights is None:
            wanted.append("the usage rights you need")
        if wanted:
            pts.append(f"Could you share {_join(wanted)}?")
        if "missing_attachment" in flags:
            pts.append("The brief doesn't seem to have come through. Could you resend it?")

    elif step == "accept":
        pts.append("I'm happy to go ahead on these terms. Please send a written agreement covering deliverables, dates, usage and payment.")

    if step in ("accept", "negotiate", "ask_for_details"):
        if "agency_unverified" in flags:
            agency = safe_text(m.on_behalf_of) or "your agency"
            pts.append(f"Before I share any details, please confirm in writing that {brand} has authorised {agency} to represent them.")
        if "sender_changed" in flags:
            pts.append("Please confirm this email comes from the same team as the earlier ones.")
    return pts


# ---------- drafts ----------
def template_draft(step: str, name: str, points: list, creator_first: str) -> str:
    return f"Hi {name},\n\n{OPENING[step]} {' '.join(points)}\n\nBest,\n{creator_first}"


def check_draft(draft: Optional[str], allowed_emails: set) -> list:
    """Return a list of problems. Empty list means the draft is safe to show."""
    if not draft or not draft.strip():
        return ["empty draft"]
    problems = []
    if URL_RE.search(draft):
        problems.append("contains a link")
    for addr in EMAIL_RE.findall(draft):
        if addr.lower() not in allowed_emails:
            problems.append(f"contains an email address ({addr})")
    if PHONE_RE.search(ISO_DATE_RE.sub("", draft)):
        problems.append("contains a phone-like number")
    if len(draft.split()) > MAX_WORDS:
        problems.append(f"longer than {MAX_WORDS} words")
    return problems


def make_gemini_llm() -> Callable:
    """Adapter around src.llm. Imported lazily so tests never need an API key."""
    from pydantic import BaseModel
    from src.llm import call_json

    class DraftOut(BaseModel):
        draft: str

    def _call(system: str, user: str) -> Optional[str]:
        r = call_json(system, user, DraftOut)
        return r.draft if r else None

    return _call


# ---------- main entry ----------
def recommend(g, profile: dict, latest_body: str = "", llm: Optional[Callable] = None) -> Recommendation:
    a, m = g.assessment, g.merged
    codes = {f.code for f in a.flags}
    step = decide_next_step(a.category, codes)
    language = detect_language(latest_body)
    if step in ("ignore", "report"):
        return Recommendation(step, language=language)

    points = reply_points(step, g, profile)
    name = (safe_text(m.contact_name, 20).split() or [safe_text(m.brand) or "there"])[0]
    creator_first = safe_text(profile["name"], 20).split()[0] if profile.get("name") else "Creator"
    template = template_draft(step, name, points, creator_first)

    rec = Recommendation(step, points, template, "template", language)
    if llm is None:
        return rec

    facts = {"next_step": step, "recipient_first_name": name, "brand": safe_text(m.brand),
             "creator_first_name": creator_first, "language": language, "points_to_include": points}
    try:
        raw = llm(DRAFT_SYSTEM, json.dumps(facts, ensure_ascii=False))
    except Exception as e:  # never let a draft failure break the pipeline
        raw, rec.draft_problems = None, [f"llm error: {e}"]
    if raw is not None or not rec.draft_problems:
        problems = check_draft(raw, {profile.get("email", "").lower()})
        if problems:
            rec.draft_problems = problems
        else:
            rec.draft, rec.draft_source = raw.strip(), "llm"
    return rec