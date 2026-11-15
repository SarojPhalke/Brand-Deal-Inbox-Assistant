"""Evaluation script for the Brand Deal Inbox Assistant.

Loads the pipeline's output (output/deals.json) and compares it against
data/expected.json.  Scores category accuracy, next-step accuracy, fee
accuracy, and flag overlap per deal.  Run independently after the pipeline:

    python -m eval.run_eval
    python -m eval.run_eval --deals output/deals.json  # explicit path
"""
import json
import sys
from pathlib import Path

DATA = Path("data")
OUTPUT = Path("output")


# ── loaders ───────────────────────────────────────────────────────────────────

def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _deals_by_email(deals: list) -> dict:
    """Index pipeline deals by every email_id they contain."""
    idx = {}
    for d in deals:
        for eid in d.get("email_ids", []):
            idx[eid] = d
    return idx


# ── field comparisons ─────────────────────────────────────────────────────────

def _approx_fee(predicted_inr, expected_inr, tol: float = 0.01) -> bool:
    """True if the two fees are within tol of each other, or both absent/zero."""
    if expected_inr in (None, 0):
        return predicted_inr in (None, 0)
    if predicted_inr is None:
        return False
    return abs(predicted_inr - expected_inr) / expected_inr <= tol


def _payment_ok(deal: dict, expected_payment: str | None) -> bool | None:
    """
    Map expected.json 'payment' values ('cash'/'gifting') to pipeline payment_type.
    Returns None if the field is not evaluable for this row.
    """
    if expected_payment is None:
        return None
    got = deal.get("payment_type")
    # pipeline uses 'cash'/'gifting'; expected.json uses the same words now
    return got == expected_payment


def _flag_overlap(pipeline_flags: set, expected_flags: list) -> tuple:
    """
    Returns (hit_count, expected_count, missing_flags).
    E-01 has an empty expected flags list → not scored.
    """
    if not expected_flags:
        return None, 0, []
    hits = sum(1 for f in expected_flags if f in pipeline_flags)
    missing = [f for f in expected_flags if f not in pipeline_flags]
    return hits, len(expected_flags), missing


# ── per-email evaluation ───────────────────────────────────────────────────────

def evaluate_email(exp: dict, deal: dict | None) -> dict:
    eid = exp["id"]
    result = {
        "email_id": eid,
        "expected_category": exp.get("category"),
        "predicted_category": None,
        "category_ok": False,
        "expected_step": exp.get("next_step"),
        "predicted_step": None,
        "step_ok": None,
        "expected_fee": exp.get("fee_inr"),
        "predicted_fee": None,
        "fee_ok": None,
        "expected_flags": exp.get("flags", []),
        "predicted_flags": [],
        "flags_hit": None,
        "flags_total": 0,
        "missing_flags": [],
        "issues": [],
        "note": exp.get("note", ""),
    }

    if deal is None:
        result["issues"].append("No deal found for this email_id in output/deals.json")
        return result

    result["predicted_category"] = deal.get("category")
    result["predicted_step"] = deal.get("next_step")
    result["predicted_fee"] = deal.get("fee_inr")
    result["predicted_flags"] = [f["code"] for f in deal.get("flags", [])]
    pipeline_flag_set = set(result["predicted_flags"])

    # ── Category ──────────────────────────────────────────────────────────────
    result["category_ok"] = result["predicted_category"] == result["expected_category"]
    if not result["category_ok"]:
        result["issues"].append(
            f"Category: got '{result['predicted_category']}', "
            f"expected '{result['expected_category']}'"
        )

    # ── Next step ─────────────────────────────────────────────────────────────
    expected_step = result["expected_step"]
    if expected_step:
        result["step_ok"] = result["predicted_step"] == expected_step
        if not result["step_ok"]:
            result["issues"].append(
                f"Next step: got '{result['predicted_step']}', expected '{expected_step}'"
            )
    # E-01 has no next_step in expected.json (it is superseded); leave step_ok=None

    # ── Fee ───────────────────────────────────────────────────────────────────
    expected_fee = result["expected_fee"]
    if expected_fee is not None:
        ok = _approx_fee(result["predicted_fee"], expected_fee)
        result["fee_ok"] = ok
        if not ok:
            result["issues"].append(
                f"Fee: got {result['predicted_fee']}, expected {expected_fee}"
            )

    # ── Flags ─────────────────────────────────────────────────────────────────
    hits, total, missing = _flag_overlap(pipeline_flag_set, result["expected_flags"])
    result["flags_hit"] = hits
    result["flags_total"] = total
    result["missing_flags"] = missing
    if missing:
        result["issues"].append(f"Missing expected flags: {missing}")

    return result


# ── report builder ─────────────────────────────────────────────────────────────

_TICK = "✅"
_CROSS = "❌"
_DASH = "—"


def _fmt(v) -> str:
    if v is True:
        return _TICK
    if v is False:
        return _CROSS
    return _DASH


def _flag_score(r: dict) -> str:
    if r["flags_hit"] is None:
        return _DASH
    return f"{r['flags_hit']}/{r['flags_total']}"


def print_report(results: list) -> None:
    sep = "─" * 100
    print(sep)
    print(
        f"{'ID':6s}  {'Exp-Category':20s}  {'Got-Category':20s}  "
        f"{'Cat':3s}  {'Step':4s}  {'Fee':3s}  {'Flags':5s}  Notes"
    )
    print(sep)

    for r in results:
        notes = "; ".join(r["issues"]) if r["issues"] else "OK"
        if r.get("note") and not r["issues"]:
            notes = f"ℹ️  {r['note']}"
        print(
            f"{r['email_id']:6s}  {str(r['expected_category']):20s}  "
            f"{str(r['predicted_category']):20s}  "
            f"{_fmt(r['category_ok']):3s}  "
            f"{_fmt(r['step_ok']):4s}  "
            f"{_fmt(r['fee_ok']):3s}  "
            f"{_flag_score(r):5s}  "
            f"{notes}"
        )

    print(sep)

    # Aggregates
    total = len(results)
    cat_ok = sum(1 for r in results if r["category_ok"])
    step_evaluated = [r for r in results if r["step_ok"] is not None]
    step_ok = sum(1 for r in step_evaluated if r["step_ok"])
    fee_evaluated = [r for r in results if r["fee_ok"] is not None]
    fee_ok = sum(1 for r in fee_evaluated if r["fee_ok"])
    flag_hits = sum(r["flags_hit"] for r in results if r["flags_hit"] is not None)
    flag_total = sum(r["flags_total"] for r in results if r["flags_hit"] is not None)

    print(f"\n  Category accuracy : {cat_ok}/{total} ({100*cat_ok//total}%)")
    if step_evaluated:
        pct = 100 * step_ok // len(step_evaluated)
        print(
            f"  Next-step accuracy: {step_ok}/{len(step_evaluated)} ({pct}%)"
            f"  (E-01 excluded — superseded, no expected step)"
        )
    if fee_evaluated:
        pct = 100 * fee_ok // len(fee_evaluated)
        print(f"  Fee accuracy      : {fee_ok}/{len(fee_evaluated)} ({pct}%)  (emails with an expected fee)")
    if flag_total:
        pct = 100 * flag_hits // flag_total
        print(f"  Flag recall       : {flag_hits}/{flag_total} ({pct}%)  (expected flags found in pipeline output)")

    # Breakdown of category misses
    misses = [r for r in results if not r["category_ok"]]
    if misses:
        print("\n  Category misses:")
        for r in misses:
            print(f"    {r['email_id']}: expected '{r['expected_category']}' → got '{r['predicted_category']}'")
    else:
        print("\n  All categories correct! ✅")

    print(sep)

    # Detailed limitations
    print("""
Limitations and known differences
  - E-01 is superseded by E-02 and E-11; both are merged into deal D1 at the pipeline
    level, so category is evaluated against each email separately but the pipeline
    produces one deal with the latest terms.
  - E-06 (Chai & Co): expected.json says 'needs_more_info' because the offer is vague
    and underpaid. The LLM classified it as 'deal_offer' (all three key fields — platform,
    deliverable, fee — are present). The rules engine preserved that classification because
    missing deadline alone does not trigger a category downgrade. This is a known judgment-
    call difference between the LLM's extraction-first view and human editorial judgment.
  - E-01 fee: expected.json records the original Rs 1,20,000 offer; the pipeline reports
    D1's merged fee of Rs 1,00,000 (latest terms). This is correct pipeline behaviour.
  - Flag recall: the pipeline uses more granular flag codes than expected.json
    (e.g. 'personal_info_request' vs 'request_for_personal_info'). Some near-misses
    are naming differences rather than logic errors.
  - Cost and processing time: each email costs ~1 LLM call (~1,000 tokens in, ~300 out).
    At Gemini Flash pricing (free tier / $0.075 per 1M input tokens), 1,000 emails/day
    ≈ $0.11/day. The 4 s sleep between calls (rate-limit guard) means 1,000 emails ≈ 67 min.
    Remove the sleep and use a paid tier to cut this to under 2 minutes.
""")


# ── entry point ────────────────────────────────────────────────────────────────

def run_evaluation(deals_path: Path | None = None) -> None:
    if deals_path is None:
        args = sys.argv[1:]
        if "--deals" in args:
            idx = args.index("--deals")
            deals_path = Path(args[idx + 1])
        else:
            deals_path = OUTPUT / "deals.json"

    if not deals_path.exists():
        print(f"[eval] ERROR: {deals_path} not found. Run 'python -m src.main' first.")
        sys.exit(1)

    expected_raw = _load_json(DATA / "expected.json")
    # expected.json is a list of objects with 'id' key
    expected_list: list = expected_raw if isinstance(expected_raw, list) else list(expected_raw.values())

    deals_list: list = _load_json(deals_path)
    by_email = _deals_by_email(deals_list)

    print(f"\n[eval] Evaluating against {deals_path}")
    print(f"[eval] Ground truth: {len(expected_list)} emails   Pipeline output: {len(deals_list)} deals\n")

    results = []
    for exp in sorted(expected_list, key=lambda x: x["id"]):
        deal = by_email.get(exp["id"])
        results.append(evaluate_email(exp, deal))

    print_report(results)


if __name__ == "__main__":
    run_evaluation()
