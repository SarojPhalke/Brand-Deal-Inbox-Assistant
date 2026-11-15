import json
import sys
import time
from pathlib import Path

from src.group import Member, group_deals, load_or_extract
from src.reply import make_gemini_llm, recommend
from src.rules import assess

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles choke on non-ASCII drafts
    data = Path("data")
    inbox = {e["id"]: e for e in json.loads((data / "inbox.json").read_text(encoding="utf-8"))}
    profile = json.loads((data / "creator_profile.json").read_text(encoding="utf-8"))
    analyses = load_or_extract()
    members = [Member(a, inbox[a.email_id], assess(a, inbox[a.email_id], profile)) for a in analyses]
    use_llm = "--llm" in sys.argv
    llm = make_gemini_llm() if use_llm else None

    for g in group_deals(members, profile):
        r = recommend(g, profile, inbox[g.latest_email_id]["body"], llm)
        print(f"{g.deal_id}  {g.brand or '-':<12} {g.assessment.category:<17} -> {r.next_step.upper()}  [{r.language}]")
        if r.draft:
            print(f"      draft ({r.draft_source}):")
            print("      " + r.draft.replace("\n", "\n      "))
        if r.draft_problems:
            print(f"      LLM draft rejected: {r.draft_problems}")
        if use_llm and r.draft:
            time.sleep(4)  # free-tier rate limit