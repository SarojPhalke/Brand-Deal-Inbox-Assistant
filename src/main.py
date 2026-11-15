"""Pipeline entry point.

Orchestrates all existing modules in order:
  1. Load data
  2. Load or generate LLM analyses (output/analyses.json is used as a cache)
  3. Build Member objects (analysis + raw email + per-email assessment)
  4. Group into deals
  5. Generate reply recommendations for each deal
  6. Build and save creator summary
  7. Save deals.json

Run from the project root:
    python -m src.main
    python -m src.main --refresh   # force re-run LLM extraction
    python -m src.main --llm       # use Gemini to draft replies
"""
import json
import sys
from pathlib import Path

from src.group import Member, group_deals, load_or_extract
from src.reply import make_gemini_llm, recommend
from src.rules import assess, inr
from src.summary import build_summary

DATA = Path("data")
OUTPUT = Path("output")


def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _deal_to_dict(group, rec) -> dict:
    """Serialise a DealGroup + Recommendation into a plain JSON-safe dict."""
    a, m = group.assessment, group.merged
    return {
        "deal_id": group.deal_id,
        "brand": m.brand,
        "email_ids": group.email_ids,
        "latest_email_id": group.latest_email_id,
        "superseded_ids": group.superseded_ids,
        "category": a.category,
        "next_step": rec.next_step,
        "language": rec.language,
        "fee_inr": a.fee_inr,
        "rate_card_inr": a.rate_card_inr,
        "fee_display": inr(a.fee_inr) if a.fee_inr else None,
        "deliverables": [
            ({"platform": d.platform, "kind": d.kind, "count": d.count}
             if hasattr(d, "platform") else d)
            for d in m.deliverables
        ],
        "deadline": m.deadline,
        "usage_rights": m.usage_rights,
        "payment_type": m.payment_type,
        "gift_value_inr": m.gift_value_inr,
        "confidence": m.confidence,
        "flags": [
            {"code": f.code, "severity": f.severity, "reason": f.reason}
            for f in a.flags
        ],
        "term_changes": group.changes,
        "reply_points": rec.points,
        "draft_reply": rec.draft,
        "draft_source": rec.draft_source,
        "draft_problems": rec.draft_problems,
        "latest_analysis": {
            "email_id": m.email_id,
            "category": m.category,
            "brand": m.brand,
            "contact_name": m.contact_name,
            "contact_email": m.contact_email,
            "on_behalf_of": m.on_behalf_of,
            "reasoning": m.reasoning,
        },
    }


def main() -> None:
    refresh = "--refresh" in sys.argv
    use_llm = "--llm" in sys.argv

    # ── 1. Load reference data ────────────────────────────────────────────────
    print("[main] Loading inbox and creator profile…")
    inbox_list: list = _load_json(DATA / "inbox.json")
    profile: dict = _load_json(DATA / "creator_profile.json")
    inbox: dict = {e["id"]: e for e in inbox_list}

    # ── 2. Extract (or load cache) ────────────────────────────────────────────
    print(f"[main] {'Refreshing' if refresh else 'Loading'} LLM analyses…")
    analyses = load_or_extract(refresh=refresh)
    print(f"[main] {len(analyses)} email(s) analysed.")

    # ── 3. Build Member objects with per-email rule assessments ───────────────
    print("[main] Running deterministic rule checks…")
    members: list[Member] = []
    for a in analyses:
        email = inbox.get(a.email_id)
        if email is None:
            print(f"[main] WARNING: no inbox entry for {a.email_id}, skipping.")
            continue
        members.append(Member(a, email, assess(a, email, profile)))

    # ── 4. Group into deals ───────────────────────────────────────────────────
    print("[main] Grouping emails into deals…")
    groups = group_deals(members, profile)
    print(f"[main] {len(groups)} deal group(s) found.")

    # ── 5. Generate recommendations and draft replies ─────────────────────────
    llm = make_gemini_llm() if use_llm else None
    if use_llm:
        print("[main] LLM draft mode ON (Gemini).")

    print("[main] Generating recommendations…")
    recommendations = []
    for g in groups:
        latest_body = inbox.get(g.latest_email_id, {}).get("body", "")
        rec = recommend(g, profile, latest_body, llm)
        recommendations.append(rec)
        step_label = rec.next_step.upper()
        print(f"  {g.deal_id:4s}  {(g.brand or '?'):14s}  {g.assessment.category:17s}  → {step_label}")

    # ── 6. Build creator summary ──────────────────────────────────────────────
    print("[main] Building summary…")
    summary_md = build_summary(groups, recommendations, profile, inbox)
    summary_path = OUTPUT / "summary.md"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary_md, encoding="utf-8")
    print(f"[main] Summary saved → {summary_path}")

    # ── 7. Save deals.json ────────────────────────────────────────────────────
    deals_list = [_deal_to_dict(g, rec) for g, rec in zip(groups, recommendations)]
    deals_path = OUTPUT / "deals.json"
    _save_json(deals_path, deals_list)
    print(f"[main] Deals saved   → {deals_path}")

    # ── 8. Console recap ──────────────────────────────────────────────────────
    print("\n── Deal summary ──────────────────────────────────────────────")
    for g, rec in zip(groups, recommendations):
        a = g.assessment
        fee = inr(a.fee_inr) if a.fee_inr else ("gifting" if g.merged.payment_type == "gifting" else "—")
        flag_codes = [f.code for f in a.flags]
        print(
            f"  {g.deal_id:4s}  {(g.brand or '?'):14s}  {a.category:17s}"
            f"  {rec.next_step:14s}  fee={fee}  flags={flag_codes}"
        )
    print("──────────────────────────────────────────────────────────────")
    print(f"\n[main] Done. Output in {OUTPUT}/")


if __name__ == "__main__":
    main()
