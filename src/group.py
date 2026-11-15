"""Group emails into deals and merge their terms (latest value wins).

Why this exists: the category belongs to the deal, not to a single email. A short
follow-up ("same deliverables, new budget") looks incomplete on its own.
"""
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.rules import FREE_EMAIL_DOMAINS, Assessment, assess, inr, sender_domain, to_inr
from src.schema import EmailAnalysis, RiskFlag

UNGROUPABLE = ("scam_or_phishing", "spam")  # never merged into a real deal


@dataclass
class Member:
    analysis: EmailAnalysis
    email: dict
    assessment: Assessment  # per-email result from rules.assess()


@dataclass
class DealGroup:
    deal_id: str
    brand: Optional[str]
    email_ids: list            # oldest -> newest
    latest_email_id: str
    superseded_ids: list
    merged: EmailAnalysis      # latest-wins terms
    assessment: Assessment     # category + flags computed on the merged terms
    changes: list = field(default_factory=list)  # human-readable term changes


# ---------- helpers ----------
def norm_brand(s: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _ts(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return datetime.min


def _groupable(m: Member) -> bool:
    return m.assessment.category not in UNGROUPABLE and bool(norm_brand(m.analysis.brand))


def _linked(a: Member, b: Member) -> bool:
    ba, bb = norm_brand(a.analysis.brand), norm_brand(b.analysis.brand)
    if ba and ba == bb:
        return True
    da, db = sender_domain(a.email["from"]), sender_domain(b.email["from"])
    # same company domain; agencies write for many brands so they never link by domain
    return (da == db and da not in FREE_EMAIL_DOMAINS
            and not a.analysis.on_behalf_of and not b.analysis.on_behalf_of)


def _cluster(members: list) -> list:
    parent = list(range(len(members)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    idx = [i for i, m in enumerate(members) if _groupable(m)]
    for x, i in enumerate(idx):
        for j in idx[x + 1:]:
            if _linked(members[i], members[j]):
                parent[find(i)] = find(j)
    clusters: dict = {}
    for i, m in enumerate(members):
        clusters.setdefault(find(i), []).append(m)
    return list(clusters.values())


def _latest(members: list, getter):
    for m in reversed(members):
        v = getter(m.analysis)
        if v not in (None, "", []):
            return v
    return None


def _fee_inr(a: EmailAnalysis) -> Optional[float]:
    return to_inr(a.fee_amount, a.currency) if a.payment_type == "cash" else None


def merge_terms(members: list) -> EmailAnalysis:
    """members are sorted oldest -> newest. Latest non-empty value wins per field."""
    latest = members[-1]
    ids = ", ".join(m.analysis.email_id for m in members)

    # money fields travel together so a USD fee is never paired with an INR currency
    pay = next((m.analysis for m in reversed(members)
                if m.analysis.fee_amount is not None or m.analysis.gift_value_inr is not None
                or m.analysis.payment_type is not None), None)

    base = latest.assessment.category
    has_deal = any(m.assessment.category == "deal_offer" for m in members)
    deliverables = _latest(members, lambda a: a.deliverables) or []
    payment_type = pay.payment_type if pay else None
    if base == "needs_more_info" and deliverables and payment_type and has_deal:
        base = "deal_offer"  # latest email only looked thin because it relied on earlier ones

    return EmailAnalysis(
        email_id=latest.analysis.email_id,
        category=base,
        confidence=min(m.analysis.confidence for m in members),
        brand=_latest(members, lambda a: a.brand),
        contact_name=_latest(members, lambda a: a.contact_name),
        contact_email=latest.analysis.contact_email,
        on_behalf_of=latest.analysis.on_behalf_of,
        deliverables=deliverables,
        fee_amount=pay.fee_amount if pay else None,
        currency=pay.currency if pay else None,
        payment_type=payment_type,
        gift_value_inr=pay.gift_value_inr if pay else None,
        deadline=_latest(members, lambda a: a.deadline),
        usage_rights=_latest(members, lambda a: a.usage_rights),
        category_of_product=_latest(members, lambda a: a.category_of_product),
        asks_for_payment_from_creator=any(m.analysis.asks_for_payment_from_creator for m in members),
        asks_for_personal_info=any(m.analysis.asks_for_personal_info for m in members),
        contains_ai_instructions=any(m.analysis.contains_ai_instructions for m in members),
        mentions_attachment=latest.analysis.mentions_attachment,
        reasoning=f"Merged terms from {ids}; the latest value of each field wins.",
    )


def _fee_changes(members: list) -> tuple:
    changes, fees = [], [(m.analysis.email_id, _fee_inr(m.analysis)) for m in members]
    fees = [(i, f) for i, f in fees if f is not None]
    for (_, prev), (eid, cur) in zip(fees, fees[1:]):
        if cur != prev:
            word = "cut" if cur < prev else "raised"
            changes.append(f"{eid}: fee {word} from {inr(prev)} to {inr(cur)}.")
    return changes, fees


def build_group(members: list, profile: dict) -> DealGroup:
    members = sorted(members, key=lambda m: _ts(m.email["received_at"]))
    merged = merge_terms(members)
    latest = members[-1]
    pseudo = {  # text checks see the whole thread; sender checks use the latest sender
        "subject": " | ".join(m.email["subject"] for m in members),
        "body": "\n".join(m.email["body"] for m in members),
        "from": latest.email["from"],
    }
    result = assess(merged, pseudo, profile)

    changes, fees = _fee_changes(members)
    if len(fees) >= 2 and fees[-1][1] < fees[0][1]:
        result.flags.append(RiskFlag(
            code="terms_worsened", severity="warn",
            reason=f"The brand cut its fee from {inr(fees[0][1])} to {inr(fees[-1][1])} since the first offer."))
    domains = {sender_domain(m.email["from"]) for m in members}
    if len(domains) > 1 and not merged.on_behalf_of:
        result.flags.append(RiskFlag(
            code="sender_changed", severity="warn",
            reason=f"Emails on this deal came from different domains ({', '.join(sorted(domains))}). Confirm they are the same brand."))

    ids = [m.analysis.email_id for m in members]
    return DealGroup(
        deal_id="", brand=merged.brand, email_ids=ids, latest_email_id=ids[-1],
        superseded_ids=ids[:-1], merged=merged, assessment=result, changes=changes)


def validate_partition(groups: list, all_ids: list) -> None:
    seen = [i for g in groups for i in g.email_ids]
    if sorted(seen) != sorted(all_ids):
        missing = sorted(set(all_ids) - set(seen))
        dupes = sorted({i for i in seen if seen.count(i) > 1})
        raise ValueError(f"Grouping is not a partition. Missing: {missing}. Duplicated: {dupes}")


def group_deals(members: list, profile: dict) -> list:
    groups = [build_group(c, profile) for c in _cluster(members)]
    # D1, D2... follow the time of each deal's first email (email_ids are oldest -> newest)
    stamp = {m.analysis.email_id: _ts(m.email["received_at"]) for m in members}
    groups.sort(key=lambda g: (stamp[g.email_ids[0]], g.email_ids[0]))
    for n, g in enumerate(groups, 1):
        g.deal_id = f"D{n}"
    validate_partition(groups, [m.analysis.email_id for m in members])
    return groups


# ---------- manual run (caches LLM output so you don't re-call Gemini) ----------
def load_or_extract(refresh: bool = False) -> list:
    path = Path("output/analyses.json")
    if path.exists() and not refresh:
        return [EmailAnalysis.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]
    from src.extract import extract_all  # imported here so tests don't need Gemini
    analyses = extract_all()
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps([a.model_dump() for a in analyses], indent=2), encoding="utf-8")
    return analyses


if __name__ == "__main__":
    data = Path("data")
    inbox = {e["id"]: e for e in json.loads((data / "inbox.json").read_text(encoding="utf-8"))}
    profile = json.loads((data / "creator_profile.json").read_text(encoding="utf-8"))
    analyses = load_or_extract(refresh="--refresh" in sys.argv)
    members = [Member(a, inbox[a.email_id], assess(a, inbox[a.email_id], profile)) for a in analyses]
    for g in group_deals(members, profile):
        a = g.assessment
        print(f"{g.deal_id}  {g.brand or '-':<14} {a.category:<17} emails={g.email_ids}")
        print(f"      fee_inr={a.fee_inr} rate_card={a.rate_card_inr} flags={[f.code for f in a.flags]}")
        for c in g.changes:
            print(f"      change: {c}")