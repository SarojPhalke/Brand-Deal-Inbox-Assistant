import json
from pathlib import Path

from src.extract import extract_all
from src.rules import assess

DATA = Path("data")

if __name__ == "__main__":
    inbox = {e["id"]: e for e in json.loads((DATA / "inbox.json").read_text(encoding="utf-8"))}
    profile = json.loads((DATA / "creator_profile.json").read_text(encoding="utf-8"))
    exp = json.loads((DATA / "expected.json").read_text(encoding="utf-8"))
    exp = {e["id"]: e for e in exp} if isinstance(exp, list) else exp
    ok = 0
    for a in extract_all():
        r = assess(a, inbox[a.email_id], profile)
        want = exp[a.email_id]["category"]
        ok += r.category == want
        mark = "OK" if r.category == want else "MISS"
        print(f"{a.email_id}  llm={a.category:<17} final={r.category:<17} want={want:<17} {mark}")
        print(f"       flags: {[f.code for f in r.flags]}")
        if r.category_changed_by:
            print(f"       overridden by: {r.category_changed_by}")
    print(f"\n{ok}/15 categories match after rules")