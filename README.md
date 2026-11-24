# Brand Deal Inbox Assistant

A command-line tool that reads a creator's brand-deal inbox and tells them **what each email is, what the deal actually says, what's risky, and what to do next**, with draft replies ready to review. Nothing is ever sent.



The design in one line: **the LLM extracts, plain code judges.**

---

## Quick start (fresh clone)

```bash
git clone https://github.com/SarojPhalke/Brand-Deal-Inbox-Assistant.git
cd Brand-Deal-Inbox-Assistant

python -m venv .venv
source .venv/Scripts/activate     # Windows Git Bash
# .venv\Scripts\activate          # Windows cmd / PowerShell
# source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
cp .env.example .env              # then paste a free Gemini key (aistudio.google.com)

python -m src.main                # writes output/summary.md and output/deals.json
python -m eval.run_eval           # scores the output against data/expected.json
pytest                            # 46 tests, no API key needed
```

- **No API key?** The repo includes my cached extraction (`output/analyses.json`), so `python -m src.main` and `python -m eval.run_eval` run offline. A key is only needed for `--refresh` or `--llm`.
- `python -m src.main --refresh` re-runs LLM extraction (15 calls, about 1 minute on the free tier).
- `python -m src.main --llm` also asks Gemini to polish the draft replies. Without it, drafts come from templates.
- Read the result in `output/summary.md`.

---

## What it does

| Capability | Detail |
|---|---|
| Classification | `deal_offer`, `needs_more_info`, `not_a_fit`, `scam_or_phishing`, `spam` |
| Structured extraction | Brand, contact, agency, deliverables, fee, currency, cash vs gifting, deadline, usage rights |
| Deal grouping | Follow-ups and agency emails are merged into one deal; the latest terms win |
| Risk flags with reasons | Below/above rate card, exclusivity conflict, content-rule violation, pay-to-join, prompt injection, lookalike domain, past deadline, unusual usage rights, gifting-only, unverified agency, fee cut since first offer, missing details or attachment |
| Next step per deal | `accept`, `negotiate`, `ask_for_details`, `decline`, `ignore`, `report` |
| Draft replies | Short, for the creator to review. Checked in code before being shown |
| Creator summary | Markdown, sorted by what needs attention today |

---

## Design: what the model does, what code does, and why

| Task | Who | Why |
|---|---|---|
| Classify and extract fields from messy text (including Hinglish) | LLM (Gemini) | Too many phrasings for rules |
| USD to INR, Indian number formats, rate-card maths, fee vs rate | Code | Must be exact |
| Exclusivity, content rules, usage rights, past-deadline checks | Code | Binary checks against the profile; must be right and testable |
| Scam overrides (pay-to-join, injection, lookalike domain) | Code, can override the LLM | A model must not be the only defence |
| Deal grouping and latest-terms merge | Code | Deterministic and auditable |
| Next step and what a reply must say | Code | Lookup over category and flags |
| Rewording the reply into natural email | LLM (optional) | Phrasing is where a model helps; output is checked |
| Creator summary | Code | Templated from structured data |

```text
inbox.json --> extract.py (LLM) --> analyses.json (cache)
                                          |
creator_profile.json --> rules.py  <------+   per-email checks, may override the LLM category
                              |
                          group.py          one deal per thread, latest terms win, rules re-run on merged terms
                              |
                          reply.py          next step + reply points (code), optional LLM wording, draft safety check
                              |
                  summary.py / main.py  --> output/summary.md, output/deals.json
```

---

## Handling untrusted email

Every email body is treated as attacker-controlled. E-07 is a direct prompt-injection test.

1. The body goes to the model only inside `<email>` tags, with the system prompt saying it is data, never instructions. Any `<email>` or `</email>` the sender types is stripped.
2. The model's reply must validate against a Pydantic schema. Invalid replies are retried, then fall back to `needs_more_info` with confidence 0; they never crash the run.
3. `email_id` and `contact_email` are set from the inbox header in code, never from the model.
4. Injection is detected by the model flag **and** a regex in `rules.py`. Code can only escalate this signal, never clear it, and it forces `scam_or_phishing` (unit-tested even when the model misses it).
5. Scam and spam emails are never merged into a real deal, so a fake "Dew Lab" email cannot hijack the real Dew Lab thread (tested).
6. Replies are built from points written by code. Names and brands from emails are sanitised before they reach the drafting prompt. An LLM draft is rejected if it contains a link, a phone-like number, an unknown email address or more than 140 words, and the template is used instead.

---

## Evaluation

**Method.** I hand-labelled all 15 emails before running anything (category, key fields, flags, next step), including the three judgment calls below. I then normalised the labels to a fixed vocabulary (with AI help) so the eval can score them mechanically. `data/expected.json` is the result.

**Scoring.**
- Category and next step: exact match.
- Fee: within 1%.
- Flags: recall of the expected flags; extra flags are not penalised.
- Each email is scored with the category of the deal that contains it. E-01 has no expected next step because it is superseded.

**Model used:** `MODEL_NAME` (Gemini free tier), temperature 0.

### Results

```text
Category accuracy : 14/15 (93%)
Next-step accuracy: 13/14 (92%)   (E-01 excluded: superseded, no expected step)
Fee accuracy      : 7/8   (87%)   (emails with an expected fee)
Flag recall       : 18/20 (90%)   (expected flags found in pipeline output)
```

| ID | Expected | Got | Cat | Step | Fee | Flags |
|---|---|---|:---:|:---:|:---:|:---:|
| E-01 | deal_offer | deal_offer | ✅ | n/a | ❌¹ | n/a |
| E-02 | deal_offer | deal_offer | ✅ | ✅ | ✅ | 1/1 |
| E-03 | scam_or_phishing | scam_or_phishing | ✅ | ✅ | n/a | 2/2 |
| E-04 | not_a_fit | not_a_fit | ✅ | ✅ | ✅ | 1/1 |
| E-05 | not_a_fit | not_a_fit | ✅ | ✅ | ✅ | 1/1 |
| **E-06** | **needs_more_info** | **deal_offer** | ❌ | ❌ | ✅ | 2/2 |
| E-07 | scam_or_phishing | scam_or_phishing | ✅ | ✅ | n/a | 1/2² |
| E-08 | needs_more_info | needs_more_info | ✅ | ✅ | n/a | 1/1 |
| E-09 | deal_offer | deal_offer | ✅ | ✅ | n/a | 2/2 |
| E-10 | deal_offer | deal_offer | ✅ | ✅ | ✅ | 1/1 |
| E-11 | deal_offer | deal_offer | ✅ | ✅ | ✅ | 2/2 |
| E-12 | needs_more_info | needs_more_info | ✅ | ✅ | ✅ | 0/1² |
| E-13 | spam | spam | ✅ | ✅ | n/a | n/a |
| E-14 | scam_or_phishing | scam_or_phishing | ✅ | ✅ | n/a | 2/2 |
| E-15 | needs_more_info | needs_more_info | ✅ | ✅ | n/a | 2/2 |

¹ E-01's expected fee is the original Rs 1,20,000. The pipeline reports the deal's latest fee (Rs 1,00,000 from E-11), which is the actionable number.

² **Label typos in my own `expected.json`, not pipeline errors.** E-07 expected `request_for_personal_info` and E-12 expected `impossible_deadline`, but the pipeline's codes are `personal_info_request` and `deadline_passed`. The eval caught this on the first run. I corrected both labels afterwards. Flag recall after the correction: **XX/20**.

### How the score got here

| Run | Change | Per-email category |
|---|---|---|
| A | First prompt; the LLM also judged "is the deadline already past?" | 13/15 (misses E-02, E-06) |
| B | Moved the deadline check out of the prompt; model only extracts | 12/15 (E-12 now misses, as expected) |
| C | Added `rules.py` overrides (past deadline, exclusivity, scam signals) | 13/15 (E-12 fixed by code) |
| D | Added deal grouping and evaluated per deal | **14/15** (E-02 fixed) |

I ran each configuration once. Categories were stable across runs for emails I had not changed; confidence scores moved slightly (E-04: 1.0 to 0.95) even at temperature 0.

I also tried adding "no timeline means `needs_more_info`" to the prompt to fix E-06. It had no effect (the model stayed at 1.0 confidence), and I did not add a code rule to force it (see below).

### The one miss and the judgment calls

**E-06 (Chai & Co), a miss.** I labelled it `needs_more_info`: Rs 25,000 for one reel is below the Rs 40,000 rate card, and the timeline, usage rights and scope are missing. The reply should ask for those and counter politely, in Hinglish. The system says `deal_offer` because the email does state a platform, a deliverable and a fee. A missing deadline alone does not trigger a downgrade in my rules, since plenty of real offers omit one. I could force the label with a rule like "below rate and no deadline means `needs_more_info`", but that would be fitting code to my own label, so I left the miss in. The model was also overconfident here, which matters for the "human review" idea later.

**E-09 (BrewBox), `deal_offer` (gifting), next step `negotiate`.** It is a real offer, but a Rs 3,500 product for one reel and two stories (Rs 60,000 at my rates) is heavily lopsided. The reply asks for a paid fee. Declining outright is also defensible; I chose to negotiate because the brand is real and the ask is small to fix.

**E-12 (SnapMeal), `needs_more_info`.** The fee (Rs 45,000) is above my rate card, but the email was sent on 10 November asking for a 1 November go-live. That is either a typo or a stale email, and I cannot know which, so the right move is to ask rather than accept or reject a viable paid deal. The LLM extracts the date; code compares it with `today` from the profile and downgrades the category.

**Other traps handled**
- **E-02 on its own** reads as incomplete ("same deliverables, new budget"). Only grouping with E-01 and E-11 fixes it, which no prompt change could do. The brand cut the fee from Rs 1,20,000 to Rs 1,00,000, which is now below the Rs 1,10,000 rate card, and the creator is told so.
- **E-04** pays well (USD 1,200 is Rs 1,00,800) but competes with the Nova Phones smartphone exclusivity until 2027-01-31. The fee is not the problem.
- **E-10** is good money (Rs 67,200 vs Rs 40,000) with bad terms (perpetual usage and whitelisting), which is why it is `negotiate`.
- **E-05**'s rate card shows Rs 1,40,000 because the model read "YouTube shoutout" as a `youtube_integration`. That is an assumption.

---

## Cost, time, and 1,000 emails a day

**What I measured:** I spent nothing (free tier). A first run of 15 extractions takes about 1 minute, almost all of it the 4-second pause I add between calls. Rules, grouping and the summary take milliseconds.

**What I did not measure:** token counts and paid pricing for the model I used, so I am not quoting a dollar figure. Reading the prompt, I estimate roughly 1,000 to 1,500 input tokens and under 300 output tokens per email, which is about 1.2M input and 0.3M output tokens a day at 1,000 emails. Multiply by the model's current price. To measure properly, log `usage_metadata` from each Gemini response in `_call_gemini`.

**Calls:** one extraction call per email, plus one optional drafting call per deal that needs a reply (about 9 of 13 deals here).

**At 1,000 emails a day:**
1. The free-tier daily request limit will probably be exceeded. Check the quota in AI Studio and move to a paid tier.
2. Sequential calls with a 4-second pause take about 67 minutes. Replace the pause with concurrency and a rate-limit semaphore.
3. Cache per email (hash of sender, subject and body) so reruns and duplicates cost nothing. Today the cache is one file per run.
4. Skip the LLM for obvious cases: run the regex scam checks first and send only the rest to the model, or use a cheaper model for them.
5. Keep retries with backoff (already in `llm.py`) and put extraction behind a queue.
6. Add a human-review queue. Model confidence is not usable for this (E-06 was wrong at 0.95 to 1.0), so use disagreement between the LLM and the rules, or a second-opinion model.
7. Grouping compares emails pairwise, which is fine for hundreds per run. For thousands, index by brand and sender domain.
8. Run incrementally per creator: extract only new emails and re-merge only the affected deals.

---

## Known limitations

- **The eval is optimistic.** I read these 15 emails before writing the rules and prompt, and 15 is small. A held-out set is the first thing I would add.
- **E-06 is wrong** (see above), and model confidence is not calibrated.
- **Two separate campaigns from the same brand would merge** into one deal. There is no "new campaign" detector.
- **Scam regexes are English-only.** A Hindi or Hinglish phishing email would rely on the model and the lookalike-domain check.
- **Template drafts are English-only.** Hinglish replies (E-06) only come from the `--llm` path.
- **Attachments are not read.** The inbox has no attachment data, so any email that mentions an attachment gets a `missing_attachment` flag (E-15).
- **Keyword content rules can false-positive** (for example "fantasy" in an unrelated sense).
- **Declined deals still show business flags** such as `above_rate`, which a creator does not care about once the deal is blocked.
- **Only INR and USD**, at the fixed rate given in the profile.

---

## What I'd build next (one more week)

1. Held-out eval set (50+ emails) written by someone other than me, plus per-run variance reporting.
2. Async extraction, per-email cache and token/cost logging.
3. Read attachments (PDF briefs) and verify agency authority with the brand.
4. A better uncertainty signal (self-consistency, or a second pass when the LLM and rules disagree) feeding a review queue.
5. Deal state across runs (new, awaiting reply, negotiating, closed) and a sent-reply ledger.
6. A "new campaign" detector for repeat brands.
7. Hinglish templates, and a small UI with copy-draft buttons.

---

## AI tools: where and how I used them

I used two AI assistants. Here is who did what.

- **Claude (chat):** planned the time-boxed approach; first drafts of `schema.py`, `llm.py`, `extract.py` (including the system prompt), `rules.py`, `group.py`, `reply.py` and their unit tests; reviewed my other files; helped structure this README.
- **Google Antigravity:** first drafts of `summary.py`, `main.py` and `eval/run_eval.py`, which I then checked against the real module signatures.

**What I did myself:** hand-labelled the 15 emails and decided E-06, E-09 and E-12 before running anything; picked the model and rate limits; ran the experiments in the table above; read every output; fixed environment and git problems; and decided to leave the E-06 miss in rather than patch it.

**Where the AI was wrong and I caught it:**
1. The suggested default model (`gemini-2.0-flash`) returned 404 on my key. I listed the models my key could use and picked one from that list.
2. I was told the "no timeline" prompt clause would fix E-06. It did nothing, so I kept the miss.
3. The first normalised `expected.json` used flag names the pipeline never emits (E-07, E-12). The eval exposed it and I corrected the labels.
4. In the Antigravity-drafted files, `eval/run_eval.py` had a hardcoded cost estimate that did not match its own arithmetic, and `summary.py` had a dead function and a hardcoded "15 emails". I removed them.

---

## Project structure

```text
Brand-Deal-Inbox-Assistant/
├── data/
│   ├── inbox.json             # 15 emails
│   ├── creator_profile.json   # rates, exclusivity, content rules, "today"
│   └── expected.json          # my labels for all 15 emails
├── src/
│   ├── schema.py              # Pydantic models
│   ├── llm.py                 # Gemini call with JSON mode, retry, schema validation
│   ├── extract.py             # per-email extraction (system prompt lives here)
│   ├── rules.py               # deterministic checks and category overrides
│   ├── group.py               # deal grouping and latest-terms merge
│   ├── reply.py               # next step, reply points, draft safety check
│   ├── summary.py             # Markdown summary (no LLM)
│   └── main.py                # pipeline entry point
├── eval/run_eval.py           # scores output/deals.json against expected.json
├── tests/                     # schema (3), rules (19), group (12), reply (12)
├── output/                    # analyses.json (cached extraction), deals.json, summary.md
├── requirements.txt
├── pytest.ini
└── .env.example
```

## Environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `GEMINI_API_KEY` | Only for `--refresh` / `--llm` | none | Free key from Google AI Studio |
| `GEMINI_MODEL` | No | `MODEL_NAME` | Model names change; list the ones your key can use if you get a 404 |

`.env` is git-ignored; never commit a real key.

## Tests

46 tests, all deterministic, no network. `test_rules.py` covers money parsing, rate-card maths, deadline, exclusivity, content rules, usage rights and scam signals, plus full overrides for E-03, E-04, E-07, E-09, E-12 and E-14. `test_group.py` covers the Dew Lab merge, input-order independence, scam emails never merging, and the partition check. `test_reply.py` covers next steps, drafts, language detection and the LLM-draft safety fallback.
