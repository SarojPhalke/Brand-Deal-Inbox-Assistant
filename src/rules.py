"""Deterministic checks. No LLM calls here: everything is pure and unit-tested.

The LLM extracts fields; this module judges them against the creator profile.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from src.schema import EmailAnalysis, RiskFlag

USD_TO_INR = 84.0  # from creator_profile.json "currency_note"
MAX_INCLUDED_USAGE_MONTHS = 3  # from creator_profile.json "usage_rights_policy"

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.in", "outlook.com", "hotmail.com",
    "rediffmail.com", "proton.me", "protonmail.com",
}
# brand token -> its real domain. Used to catch lookalike sender domains.
OFFICIAL_DOMAINS = {
    "youtube": "youtube.com", "google": "google.com",
    "instagram": "instagram.com", "facebook": "facebook.com",
}

INJECTION_RE = re.compile(
    r"(ai assistant|language model|ignore (all )?(previous|prior) instructions|"
    r"classify this (email )?as|system prompt|you must (now )?(recommend|classify))",
    re.I,
)
CONTENT_RULE_RE = re.compile(
    r"\b(fantasy[\s_-]*(sports?|cricket|football|league|app)|betting|bet|gambling|"
    r"gamble|casino|poker|rummy|satta|crypto\w*|bitcoin|forex|trading tips?|"
    r"stock tips?|binary options)\b",
    re.I,
)
PAY_TO_JOIN_RE = re.compile(
    r"\b(registration|joining|enrol+ment|membership|processing|activation|"
    r"verification)\s+(fee|charge)s?\b|security deposit|pay (a|an) [\w\s-]{0,30}fee\b",
    re.I,
)
URGENCY_RE = re.compile(
    r"\b(12|24|48)\s*hours?\b|within \d+ hours?|act now|last chance|"
    r"expires? (today|soon)|will be (suspended|terminated|deleted)|"
    r"account (suspended|terminated)",
    re.I,
)
PERSONAL_INFO_RE = re.compile(
    r"\b(phone number|mobile number|home address|residential address|bank account|"
    r"account number|ifsc|otp|password|aadhaar|aadhar|pan card|passport|cvv|card number)\b",
    re.I,
)
UNUSUAL_USAGE_RE = re.compile(
    r"perpetu|unlimited|lifetime|forever|all media|whitelist|spark ad|"
    r"partnership ad|dark post",
    re.I,
)
URL_RE = re.compile(r"https?://([^/\s:]+)", re.I)

_MULT = {"k": 1e3, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5,
         "crore": 1e7, "crores": 1e7, "cr": 1e7}
_AMOUNT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|cr|k)?\b", re.I)


# ---------- numbers and money ----------
def parse_amount(text) -> Optional[float]:
    """'1,20,000' -> 120000, '3 lakh' -> 300000, 'USD 1,200' -> 1200."""
    if text is None:
        return None
    m = _AMOUNT_RE.search(str(text))
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    return value * _MULT.get(unit, 1)


def to_inr(amount: Optional[float], currency: Optional[str]) -> Optional[float]:
    if amount is None:
        return None
    return amount * USD_TO_INR if currency == "USD" else amount  # None -> assume INR


def inr(x: float) -> str:
    """Indian digit grouping. Uses 'Rs' because Windows consoles can choke on the rupee sign."""
    s = str(int(round(x)))
    if len(s) <= 3:
        return f"Rs {s}"
    head, tail = s[:-3], s[-3:]
    head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
    return f"Rs {head},{tail}"


def _d(d):
    if isinstance(d, dict):
        return d["platform"], d["kind"], int(d.get("count", 1))
    return d.platform, d.kind, int(d.count)


def rate_card_value(deliverables, profile: dict) -> Optional[float]:
    """Sum of base rates for the deliverables. None if any deliverable is unknown."""
    rates = profile["base_rates_inr"]
    if not deliverables:
        return None
    total = 0.0
    for d in deliverables:
        platform, kind, count = _d(d)
        key = f"{platform}_{kind}".lower().replace(" ", "_")
        if key not in rates:
            return None
        total += rates[key] * count
    return total


def compare_fee(offer_inr: Optional[float], rate_inr: Optional[float]) -> Optional[RiskFlag]:
    if offer_inr is None or rate_inr is None:
        return None
    diff = offer_inr - rate_inr
    if diff < 0:
        return RiskFlag(code="below_rate", severity="warn",
                        reason=f"Offer {inr(offer_inr)} is {inr(-diff)} below your rate card ({inr(rate_inr)}).")
    if diff > 0:
        return RiskFlag(code="above_rate", severity="info",
                        reason=f"Offer {inr(offer_inr)} is {inr(diff)} above your rate card ({inr(rate_inr)}).")
    return None


# ---------- dates ----------
def _parse_date(s) -> Optional[date]:
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def check_deadline(deadline: Optional[str], today: str) -> list[RiskFlag]:
    d, t = _parse_date(deadline), _parse_date(today)
    if not d or not t:
        return []
    if d < t:
        return [RiskFlag(code="deadline_passed", severity="block",
                         reason=f"Deadline {d.isoformat()} is before today ({t.isoformat()}). Typo or old email?")]
    if (d - t).days < 3:
        return [RiskFlag(code="tight_deadline", severity="warn",
                         reason=f"Only {(d - t).days} day(s) until the deadline.")]
    return []


# ---------- profile conflicts ----------
def _norm_product(s) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower()).rstrip("s")


def check_exclusivity(product: Optional[str], deadline: Optional[str], profile: dict) -> Optional[RiskFlag]:
    p = _norm_product(product)
    if not p:
        return None
    d = _parse_date(deadline)
    for ex in profile["current_exclusivity"]:
        c = _norm_product(ex["category"])
        if c and (p in c or c in p):
            until = _parse_date(ex["until"])
            if d and until and d > until:
                continue  # content goes live after the exclusivity ends
            return RiskFlag(code="exclusivity_conflict", severity="block",
                            reason=f"Competes with your {ex['brand']} exclusivity ({ex['category']}) until {ex['until']}.")
    return None


def check_content_rules(text: str) -> Optional[RiskFlag]:
    m = CONTENT_RULE_RE.search(text or "")
    if not m:
        return None
    return RiskFlag(code="content_rule_violation", severity="block",
                    reason=f"Mentions '{m.group(0)}', which breaks your content rules (gambling, betting, fantasy sports, crypto).")


def check_usage_rights(usage: Optional[str]) -> Optional[RiskFlag]:
    if not usage:
        return None
    reasons = []
    if UNUSUAL_USAGE_RE.search(usage):
        reasons.append("perpetual, all-media or whitelisting-style usage")
    for n, unit in re.findall(r"(\d+)\s*(month|year)s?", usage, re.I):
        months = int(n) * (12 if unit.lower() == "year" else 1)
        if months > MAX_INCLUDED_USAGE_MONTHS:
            reasons.append(f"{months} months of usage")
    if not reasons:
        return None
    return RiskFlag(code="unusual_usage_rights", severity="warn",
                    reason=f"Asks for {' and '.join(reasons)}; your rate includes up to {MAX_INCLUDED_USAGE_MONTHS} months of paid-ad usage. Price extra usage separately.")


# ---------- scam signals ----------
def check_injection(analysis: EmailAnalysis, text: str) -> Optional[RiskFlag]:
    if analysis.contains_ai_instructions or INJECTION_RE.search(text or ""):
        return RiskFlag(code="prompt_injection", severity="block",
                        reason="The email contains instructions aimed at an AI assistant. Treated as an attack, not a deal.")
    return None


def check_pay_to_join(analysis: EmailAnalysis, text: str) -> Optional[RiskFlag]:
    if analysis.asks_for_payment_from_creator or PAY_TO_JOIN_RE.search(text or ""):
        return RiskFlag(code="pay_to_join", severity="block",
                        reason="Asks you to pay a fee to join or unlock a deal. You never pay to join.")
    return None


def check_personal_info(text: str) -> Optional[RiskFlag]:
    m = PERSONAL_INFO_RE.search(text or "")
    if m:
        return RiskFlag(code="personal_info_request", severity="warn",
                        reason=f"Asks for sensitive personal details ('{m.group(0)}').")
    return None


def check_urgency(text: str) -> Optional[RiskFlag]:
    if URGENCY_RE.search(text or ""):
        return RiskFlag(code="urgency_pressure", severity="warn",
                        reason="Uses artificial time pressure to rush you.")
    return None


def sender_domain(addr: str) -> str:
    return (addr or "").rsplit("@", 1)[-1].strip(" >").lower()


def check_lookalike_domain(sender: str) -> Optional[RiskFlag]:
    d = sender_domain(sender)
    for token, official in OFFICIAL_DOMAINS.items():
        if token in d and not (d == official or d.endswith("." + official)):
            return RiskFlag(code="suspicious_link", severity="block",
                            reason=f"Sender domain '{d}' imitates {token.title()} but is not {official}.")
    return None


def check_links(sender: str, body: str) -> Optional[RiskFlag]:
    d = sender_domain(sender)
    for host in URL_RE.findall(body or ""):
        host = host.lower()
        if host != d and not host.endswith("." + d):
            return RiskFlag(code="suspicious_link", severity="warn",
                            reason=f"Links to '{host}', which is not the sender's domain.")
    return None


def check_free_email(sender: str) -> Optional[RiskFlag]:
    if sender_domain(sender) in FREE_EMAIL_DOMAINS:
        return RiskFlag(code="free_email_domain", severity="info",
                        reason="Sent from a free email address, not a company domain. Verify the brand.")
    return None


# ---------- completeness ----------
def missing_fields(a: EmailAnalysis) -> list[str]:
    m = []
    if not a.deliverables:
        m.append("deliverables")
    if a.payment_type is None:
        m.append("compensation")
    if not a.deadline:
        m.append("timeline")
    return m


# ---------- orchestration ----------
@dataclass
class Assessment:
    category: str
    flags: list[RiskFlag]
    fee_inr: Optional[float]
    rate_card_inr: Optional[float]
    category_changed_by: Optional[str] = None  # which rule overrode the LLM


def assess(a: EmailAnalysis, email: dict, profile: dict) -> Assessment:
    text = f"{email['subject']} {email['body']}"
    sender = email["from"]

    safety = [f for f in (
        check_injection(a, text),
        check_pay_to_join(a, text),
        check_lookalike_domain(sender),
        check_links(sender, email["body"]),
        check_personal_info(text),
        check_urgency(text),
    ) if f]
    scam_codes = {f.code for f in safety if f.severity == "block"}
    codes = {f.code for f in safety}

    profile_flags = [f for f in (
        check_exclusivity(a.category_of_product, a.deadline, profile),
        check_content_rules(f"{a.category_of_product or ''} {a.brand or ''} {text}"),
    ) if f]

    category, changed_by = a.category, None
    if category not in ("scam_or_phishing", "spam"):
        if scam_codes or {"personal_info_request", "urgency_pressure"} <= codes:
            category = "scam_or_phishing"
            changed_by = "scam rule: " + ", ".join(sorted(scam_codes or codes))
        elif profile_flags:
            category = "not_a_fit"
            changed_by = "profile rule: " + ", ".join(f.code for f in profile_flags)

    deadline_flags = check_deadline(a.deadline, profile["today"])
    if category == "deal_offer" and any(f.code == "deadline_passed" for f in deadline_flags):
        category, changed_by = "needs_more_info", "deadline already passed"

    flags = list(safety)
    fee_inr = to_inr(a.fee_amount, a.currency) if a.payment_type == "cash" else None
    rate = rate_card_value(a.deliverables, profile)

    if category not in ("scam_or_phishing", "spam"):
        flags += profile_flags + deadline_flags
        offer = fee_inr if a.payment_type == "cash" else a.gift_value_inr
        if a.payment_type == "gifting":
            flags.append(RiskFlag(code="gifting_only", severity="warn",
                                  reason="Payment is in products only, no cash."))
        flags += [f for f in (compare_fee(offer, rate),
                              check_usage_rights(a.usage_rights),
                              check_free_email(sender)) if f]
        if a.on_behalf_of:
            flags.append(RiskFlag(code="agency_unverified", severity="warn",
                                  reason=f"Written by {a.on_behalf_of} on behalf of the brand. Confirm with the brand before sharing details."))
        if a.mentions_attachment:
            flags.append(RiskFlag(code="missing_attachment", severity="warn",
                                  reason="Mentions an attachment, but none came through."))
        missing = missing_fields(a)
        if missing:
            sev = "warn" if set(missing) & {"deliverables", "compensation"} else "info"
            flags.append(RiskFlag(code="missing_details", severity=sev,
                                  reason=f"Missing: {', '.join(missing)}."))

    return Assessment(category, flags, fee_inr, rate, changed_by)