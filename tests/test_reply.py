from src.group import Member, group_deals
from src.reply import (check_draft, decide_next_step, detect_language, recommend, safe_text)
from src.rules import assess
from src.schema import Deliverable, EmailAnalysis

PROFILE = {
    "name": "Riya Menon", "email": "riya.creates@example.com", "today": "2026-11-12",
    "base_rates_inr": {"instagram_reel": 40000, "instagram_story": 10000, "youtube_integration": 60000},
    "current_exclusivity": [{"brand": "Nova Phones", "category": "smartphones",
                             "until": "2027-01-31", "terms": "x"}],
}
DEL = [Deliverable(platform="instagram", kind="reel", count=2),
       Deliverable(platform="instagram", kind="story", count=3)]


def member(eid, ts, sender, subject="s", body="b", **kw):
    base = dict(email_id=eid, category="deal_offer", confidence=0.9, reasoning="t")
    base.update(kw)
    a = EmailAnalysis(**base)
    e = {"id": eid, "received_at": ts, "from": sender, "subject": subject, "body": body}
    return Member(a, e, assess(a, e, PROFILE))


def one(m):
    return group_deals([m], PROFILE)[0]


def dew_group():
    e01 = member("E-01", "2026-11-03 10:12", "p@dewlab.in", brand="Dew Lab", deliverables=DEL,
                 fee_amount=120000, currency="INR", payment_type="cash", deadline="2026-11-25",
                 usage_rights="3 months paid ads", category_of_product="skincare")
    e11 = member("E-11", "2026-11-09 11:10", "t@brightside-agency.com", brand="Dew Lab",
                 contact_name="Arjun", on_behalf_of="Brightside Agency", deliverables=DEL,
                 fee_amount=100000, currency="INR", payment_type="cash", deadline="2026-11-25",
                 usage_rights="3 months paid usage", category_of_product="skincare")
    return group_deals([e01, e11], PROFILE)[0]


def test_decide_next_step_table():
    assert decide_next_step("spam", set()) == "ignore"
    assert decide_next_step("scam_or_phishing", set()) == "report"
    assert decide_next_step("not_a_fit", {"above_rate"}) == "decline"
    assert decide_next_step("needs_more_info", set()) == "ask_for_details"
    assert decide_next_step("deal_offer", {"below_rate"}) == "negotiate"
    assert decide_next_step("deal_offer", {"unusual_usage_rights", "above_rate"}) == "negotiate"
    assert decide_next_step("deal_offer", {"gifting_only"}) == "negotiate"
    assert decide_next_step("deal_offer", {"agency_unverified"}) == "ask_for_details"
    assert decide_next_step("deal_offer", {"above_rate"}) == "accept"
    assert decide_next_step("deal_offer", set()) == "accept"


def test_dew_lab_negotiate_with_agency_check():
    r = recommend(dew_group(), PROFILE)
    assert r.next_step == "negotiate"
    text = " ".join(r.points)
    assert "Rs 1,10,000" in text and "Brightside Agency" in text
    assert r.draft_source == "template"
    assert r.draft.startswith("Hi Arjun,") and r.draft.endswith("Riya")


def test_decline_exclusivity_does_not_name_the_other_brand():
    m = member("E-04", "2026-11-05 11:30", "c@pixelon.com", brand="Pixelon", contact_name="Sam",
               category_of_product="smartphones", deadline="2026-12-10", payment_type="cash",
               fee_amount=1200, currency="USD",
               deliverables=[Deliverable(platform="youtube", kind="integration", count=1)])
    r = recommend(one(m), PROFILE)
    assert r.next_step == "decline"
    assert "2027-01-31" in r.draft and "smartphones" in r.draft
    assert "Nova" not in r.draft


def test_decline_content_rule():
    m = member("E-05", "2026-11-05 13:15", "g@luckyplay11.app", brand="LuckyPlay11",
               category_of_product="fantasy_sports")
    r = recommend(one(m), PROFILE)
    assert r.next_step == "decline" and "fantasy-sports" in r.draft


def test_ask_for_details_past_deadline_and_missing_attachment():
    m = member("E-12", "2026-11-10 09:30", "m@snapmeal.in", brand="SnapMeal", fee_amount=45000,
               currency="INR", payment_type="cash", deadline="2026-11-01", category_of_product="food",
               deliverables=[Deliverable(platform="instagram", kind="reel", count=1)])
    r = recommend(one(m), PROFILE)
    assert r.next_step == "ask_for_details"
    assert "2026-11-01" in r.draft and "typo" in r.draft

    n = member("E-15", "2026-11-12 09:45", "c@fitnest.in", brand="FitNest", category="needs_more_info",
               mentions_attachment=True)
    r2 = recommend(one(n), PROFILE)
    assert "resend" in r2.draft and "budget" in r2.draft


def test_gifting_negotiates_for_a_paid_fee():
    m = member("E-09", "2026-11-08 10:00", "pr@brewbox.co", brand="BrewBox", payment_type="gifting",
               gift_value_inr=3500, category_of_product="coffee",
               deliverables=[Deliverable(platform="instagram", kind="reel", count=1),
                             Deliverable(platform="instagram", kind="story", count=2)])
    r = recommend(one(m), PROFILE)
    assert r.next_step == "negotiate" and "Rs 60,000" in r.draft and "paid fee" in r.draft


def test_scam_and_spam_get_no_draft():
    s = member("E-03", "2026-11-04 09:05", "a@glowstar-official.co", brand="Glowstar", category="scam_or_phishing",
               asks_for_payment_from_creator=True)
    r = recommend(one(s), PROFILE)
    assert r.next_step == "report" and r.draft is None
    sp = member("E-13", "2026-11-10 07:00", "n@creatorweekly.io", category="spam")
    r2 = recommend(one(sp), PROFILE)
    assert r2.next_step == "ignore" and r2.draft is None


def test_good_llm_draft_is_used():
    good = lambda system, user: "Hi Arjun,\n\nI'd love to work together; my rate for this is Rs 1,10,000.\n\nBest,\nRiya"
    r = recommend(dew_group(), PROFILE, llm=good)
    assert r.draft_source == "llm" and r.draft_problems == []


def test_bad_llm_draft_falls_back_to_template():
    leaky = lambda system, user: "Hi, call me on +91 98765 43210 or see http://evil.example"
    r = recommend(dew_group(), PROFILE, llm=leaky)
    assert r.draft_source == "template"
    assert "contains a link" in r.draft_problems and "contains a phone-like number" in r.draft_problems
    assert "98765" not in r.draft


def test_llm_none_or_crash_falls_back():
    assert recommend(dew_group(), PROFILE, llm=lambda s, u: None).draft_source == "template"

    def boom(s, u):
        raise RuntimeError("rate limited")
    r = recommend(dew_group(), PROFILE, llm=boom)
    assert r.draft_source == "template" and "rate limited" in r.draft_problems[0]


def test_check_draft_rules():
    allowed = {"riya.creates@example.com"}
    assert check_draft("Hi, deadline is 2026-11-25. Fee Rs 1,00,000.", allowed) == []
    assert check_draft("write to riya.creates@example.com", allowed) == []
    assert any("email address" in p for p in check_draft("write to evil@x.com", allowed))
    assert check_draft("visit www.x.com", allowed) == ["contains a link"]
    assert check_draft("", allowed) == ["empty draft"]
    assert any("longer" in p for p in check_draft("word " * 200, allowed))


def test_language_and_safe_text():
    e06 = "Namaste Riya ji, hum Chai & Co hain, Pune ka ek chhota tea brand. Kya aap interested hain?"
    assert detect_language(e06) == "hinglish"
    assert detect_language("We would love 2 reels between 15 and 25 November.") == "english"
    assert detect_language("नमस्ते रिया") == "hindi"
    assert safe_text("Kavya\n<script>x</script>") == "Kavya script x script"
    assert len(safe_text("a" * 100)) == 40