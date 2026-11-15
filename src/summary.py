"""Creator-facing Markdown summary.

Consumes the list of DealGroup objects produced by group.py and generates a
human-readable Markdown report that a creator can read in under two minutes.
No LLM calls here: all the judgment has already happened upstream.
"""

from datetime import date
from typing import Optional

from src.rules import inr


# ── helpers ──────────────────────────────────────────────────────────────────

def _today_str(profile: dict) -> str:
    return profile.get("today", date.today().isoformat())


def _flag_block(flags) -> str:
    if not flags:
        return ""
    lines = []
    icons = {"block": "🚫", "warn": "⚠️", "info": "ℹ️"}
    for f in flags:
        lines.append(f"  - {icons.get(f.severity, '•')} **{f.code}**: {f.reason}")
    return "\n".join(lines)


def _money_line(group) -> str:
    a, m = group.assessment, group.merged
    parts = []
    if a.fee_inr is not None:
        parts.append(f"Fee: **{inr(a.fee_inr)}**")
    elif m.payment_type == "gifting" and m.gift_value_inr:
        parts.append(f"Gifting only — product value ~{inr(m.gift_value_inr)}")
    if a.rate_card_inr is not None:
        parts.append(f"Rate card: {inr(a.rate_card_inr)}")
    return " · ".join(parts) if parts else "Fee: not stated"


def _deliverables_line(merged) -> str:
    if not merged.deliverables:
        return "Deliverables: not stated"
    items = []
    for d in merged.deliverables:
        platform, kind, count = (
            (d["platform"], d["kind"], d.get("count", 1))
            if isinstance(d, dict)
            else (d.platform, d.kind, d.count)
        )
        label = f"{count}× {platform} {kind}"
        items.append(label)
    return "Deliverables: " + ", ".join(items)


def _deadline_line(merged) -> str:
    if not merged.deadline:
        return ""
    return f"Deadline: {merged.deadline}"


def _next_step_label(step: str) -> str:
    return {
        "accept": "✅ Ready to accept",
        "negotiate": "🔄 Negotiate terms",
        "ask_for_details": "❓ Ask for details",
        "decline": "❌ Decline",
        "ignore": "🗑️ Ignore",
        "report": "🚨 Report as scam/phishing",
    }.get(step, step.upper())


def _category_emoji(cat: str) -> str:
    return {
        "deal_offer": "💼",
        "needs_more_info": "❓",
        "not_a_fit": "🚫",
        "scam_or_phishing": "🚨",
        "spam": "🗑️",
    }.get(cat, "•")


# ── section builders ──────────────────────────────────────────────────────────



def _deal_section_with_rec(group, rec, inbox: dict) -> str:
    a, m = group.assessment, group.merged
    brand = m.brand or "Unknown Brand"

    lines = [
        f"### {group.deal_id} · {_category_emoji(a.category)} {brand}",
        "",
        f"**Category:** `{a.category}` · **Next step:** {_next_step_label(rec.next_step)}",
    ]

    # Money and scope
    money = _money_line(group)
    delivs = _deliverables_line(m)
    deadline = _deadline_line(m)
    scope_parts = [money, delivs]
    if deadline:
        scope_parts.append(deadline)
    lines.append(" · ".join(p for p in scope_parts if p))

    # Thread info
    if len(group.email_ids) > 1:
        lines.append(f"*Thread: {', '.join(group.email_ids)} · {len(group.email_ids)} emails*")

    # Flags
    flag_text = _flag_block(a.flags)
    if flag_text:
        lines.append("")
        lines.append(flag_text)

    # Term changes in this deal's thread
    for c in group.changes:
        lines.append(f"  - 📝 {c}")

    # Draft reply
    if rec.draft:
        lang_note = f" *(language: {rec.language})*" if rec.language != "english" else ""
        lines.append("")
        lines.append(f"**Draft reply{lang_note}** `[{rec.draft_source}]`:")
        lines.append("")
        lines.append("> " + rec.draft.replace("\n", "\n> "))

    lines.append("")
    return "\n".join(lines)


# ── main entry point ──────────────────────────────────────────────────────────

def build_summary(groups: list, recommendations: list, profile: dict, inbox: dict) -> str:
    """Generate the Markdown creator summary.

    Args:
        groups: list of DealGroup objects from group.group_deals().
        recommendations: list of Recommendation objects, same order as groups.
        profile: creator profile dict.
        inbox: {email_id: email_dict} from inbox.json.

    Returns:
        str: Full Markdown document.
    """
    today = _today_str(profile)
    creator_name = profile.get("name", "Creator")

    # Partition groups by urgency bucket
    urgent, action_needed, fyi, noise = [], [], [], []

    for g, rec in zip(groups, recommendations):
        cat = g.assessment.category
        step = rec.next_step
        flag_codes = {f.code for f in g.assessment.flags}

        if cat in ("scam_or_phishing", "spam"):
            noise.append((g, rec))
        elif cat == "not_a_fit":
            fyi.append((g, rec))
        elif step in ("accept", "negotiate", "ask_for_details"):
            # Check deadline urgency
            deadline = g.merged.deadline
            days_left: Optional[int] = None
            if deadline:
                try:
                    d = date.fromisoformat(deadline[:10])
                    t = date.fromisoformat(today[:10])
                    days_left = (d - t).days
                except (ValueError, TypeError):
                    pass

            is_urgent = (
                "tight_deadline" in flag_codes
                or "deadline_passed" in flag_codes
                or (days_left is not None and days_left <= 5)
            )
            if is_urgent:
                urgent.append((g, rec))
            else:
                action_needed.append((g, rec))
        else:
            fyi.append((g, rec))

    lines = [
        f"# 📬 Brand Inbox Summary — {today}",
        f"*Generated for {creator_name}*",
        "",
    ]

    # Quick stats bar
    #total_deals = sum(1 for g, _ in urgent + action_needed if g.assessment.category == "deal_offer")
    potential_inr = sum(
        (g.assessment.fee_inr or 0)
        for g, _ in urgent + action_needed
        if g.assessment.category == "deal_offer" and g.assessment.fee_inr
    )
    lines += [
        "## 📊 At a Glance",
        "",
        f"| | |",
        f"|---|---|",
        f"| Total emails processed | **{sum(len(g.email_ids) for g in groups)}** |",
        f"| Active deals | **{len(urgent) + len(action_needed)}** |",
        f"| Needs your reply | **{len(urgent) + len(action_needed)}** |",
        f"| Not a fit | **{len([x for x in fyi if x[0].assessment.category == 'not_a_fit'])}** |",
        f"| Scam / spam filtered | **{len(noise)}** |",
        f"| Potential revenue | **{inr(potential_inr)}** |" if potential_inr else f"| Potential revenue | — |",
        "",
    ]

    # ── URGENT ───────────────────────────────────────────────────────────────
    if urgent:
        lines.append("## 🔴 Needs Attention Today")
        lines.append("")
        for g, rec in urgent:
            lines.append(_deal_section_with_rec(g, rec, inbox))
    else:
        lines += ["## 🔴 Needs Attention Today", "", "*Nothing is due today.*", ""]

    # ── ACTION NEEDED ─────────────────────────────────────────────────────────
    if action_needed:
        lines.append("## 🟡 Action Needed")
        lines.append("")
        for g, rec in action_needed:
            lines.append(_deal_section_with_rec(g, rec, inbox))

    # ── NOT A FIT / FYI ──────────────────────────────────────────────────────
    if fyi:
        lines.append("## 🔵 Reviewed — No Action Needed")
        lines.append("")
        for g, rec in fyi:
            lines.append(_deal_section_with_rec(g, rec, inbox))

    # ── NOISE ─────────────────────────────────────────────────────────────────
    if noise:
        lines.append("## 🗑️ Filtered Out (Scam / Spam)")
        lines.append("")
        for g, rec in noise:
            a, m = g.assessment, g.merged
            brand = m.brand or "Unknown"
            ids = ", ".join(g.email_ids)
            top_flag = g.assessment.flags[0].reason if g.assessment.flags else "Filtered automatically."
            lines.append(f"- **{ids}** ({brand}): {top_flag}")
        lines.append("")

    # ── FOOTER ────────────────────────────────────────────────────────────────
    lines += [
        "---",
        "",
        "> *Drafts are for review only — nothing is sent automatically.*  ",
        "> *Flags marked 🚫 are blocking issues; ⚠️ need your judgment; ℹ️ are informational.*",
        "",
    ]

    return "\n".join(lines)
