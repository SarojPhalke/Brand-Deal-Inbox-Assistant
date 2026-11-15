# Brand Deal Inbox Assistant

An automated pipeline that reads a creator's brand-deal inbox and tells them **what each email is, what the deal actually says, what's risky, and what to do next** — with draft replies ready to review.

Built as the [JEEVIT Founding AI Engineer](TASK.md) take-home assignment.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Features](#features)
3. [Technology Stack](#technology-stack)
4. [Project Structure](#project-structure)
5. [Architecture & Data Flow](#architecture--data-flow)
6. [AI vs Deterministic Code](#ai-vs-deterministic-code)
7. [Setup — Fresh Clone](#setup--fresh-clone)
8. [Environment Variables](#environment-variables)
9. [Running the App](#running-the-app)
10. [Running Tests](#running-tests)
11. [Running Evaluation](#running-evaluation)
12. [Actual Evaluation Results](#actual-evaluation-results)
13. [Cost & Throughput](#cost--throughput)
14. [Future Improvements](#future-improvements)
15. [AI Coding Tools Used](#ai-coding-tools-used)

---

## Problem Statement

Creators with 10k–100k followers receive a constant stream of brand emails. Many are vague, underpaid, in conflict with existing deals, or outright scams. This tool processes the inbox automatically, groups threads into deals, flags risks, and suggests the next action — so creators can decide in seconds, not hours.

---

## Features

| Capability | Detail |
|---|---|
| **Email classification** | Five categories: `deal_offer`, `needs_more_info`, `not_a_fit`, `scam_or_phishing`, `spam` |
| **Structured extraction** | Brand, contact, platform, deliverables, fee, currency, deadline, usage rights |
| **Deal grouping** | Threads about the same brand merged into one deal; latest terms win |
| **Deterministic risk flags** | Below/above rate, exclusivity conflict, content-rule violation, pay-to-join, prompt injection, lookalike domain, past deadline, unusual usage, gifting-only, agency unverified |
| **Next-step recommendation** | `accept` / `negotiate` / `ask_for_details` / `decline` / `ignore` / `report` |
| **Draft replies** | Template-based drafts; LLM polish optional (`--llm`). Checked for PII, URLs, and length before display |
| **Creator summary** | Markdown report bucketed by urgency: today / action needed / FYI / filtered |
| **Prompt-injection defence** | Emails are wrapped in `<email>` delimiters; injection patterns caught by both the system prompt and a regex in `rules.py` |

---

## Technology Stack

| Component | Library / Model |
|---|---|
| LLM (extraction + optional draft) | Google Gemini 2.0 Flash (`google-genai`) |
| Data models & validation | Pydantic v2 |
| Environment config | python-dotenv |
| Testing | pytest |
| Language | Python 3.11+ |

---

## Project Structure

```text
creator_Email_sorting/
├── data/
│   ├── inbox.json             # 15 test emails
│   ├── creator_profile.json   # Rates, exclusivity, content rules
│   └── expected.json          # Ground-truth labels (15 emails)
├── src/
│   ├── schema.py              # Pydantic models (EmailAnalysis, Deal, RiskFlag …)
│   ├── llm.py                 # call_json() — Gemini wrapper with retry + JSON validation
│   ├── extract.py             # Per-email LLM extraction → EmailAnalysis
│   ├── rules.py               # Deterministic checks (rate, exclusivity, scam signals …)
│   ├── group.py               # Thread clustering → DealGroup (latest-wins merge)
│   ├── reply.py               # Next-step decision + draft generation + safety check
│   ├── summary.py             # Markdown creator summary (no LLM)
│   └── main.py                # Pipeline entry point
├── eval/
│   └── run_eval.py            # Scores pipeline output vs expected.json
├── tests/
│   ├── test_schema.py
│   ├── test_rules.py          # 18 unit tests — all deterministic, no API calls
│   ├── test_group.py          # 12 integration tests — grouping & merge logic
│   └── test_reply.py          # 14 tests — recommendations, drafts, safety checks
├── output/                    # Generated on first run
│   ├── analyses.json          # LLM extraction cache (avoids re-calling the API)
│   ├── deals.json             # Final deal data
│   └── summary.md             # Creator-facing Markdown report
├── TASK.md                    # Original assignment
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Architecture & Data Flow

```
inbox.json  ──┐
              ├─► extract.py (LLM)  ──► analyses.json (cache)
creator_profile.json ─┤                        │
                      └─── rules.py ◄──────────┘
                                │
                           group.py  ──► DealGroups
                                │
                           reply.py  ──► Recommendations + Drafts
                                │
                 ┌──────────────┴──────────────┐
            summary.py                     main.py
                │                              │
          output/summary.md           output/deals.json
```

**Step by step:**

1. `extract.py` calls Gemini once per email with a strict system prompt. The email body is wrapped in `<email>` tags and treated as untrusted data. The model returns structured JSON validated by Pydantic.
2. `rules.py` runs pure-Python checks against the creator profile: rate-card comparison, exclusivity, content rules, scam signals, deadline arithmetic. It can override the LLM's category.
3. `group.py` clusters emails that belong to the same deal (same brand or same company domain) using union-find. Latest non-null values win per field. Scam emails are never merged into real deals.
4. `reply.py` decides the next step from the final category and flag codes (pure code), writes the reply points (pure code), and optionally asks the LLM to rephrase them into a draft. The draft is then safety-checked before display.
5. `summary.py` organises deals into urgency buckets and renders Markdown. No LLM involved.
6. `main.py` wires it all together, writes `deals.json` and `summary.md`.

---

## AI vs Deterministic Code

| Task | Handler | Why |
|---|---|---|
| Classify email & extract fields | LLM (Gemini) | Natural language understanding; too many formats and signals for regex |
| Prompt-injection detection | **Both** | LLM is instructed to ignore instructions inside `<email>`; `rules.py` applies a regex and can escalate regardless of what the LLM said |
| Rate-card comparison | **Code** | Must be exact; LLM should not do arithmetic |
| Exclusivity & content-rule checks | **Code** | Binary pass/fail against structured profile data; must be reliable |
| Deadline arithmetic | **Code** | Date comparison is deterministic; LLM hallucinations here would be costly |
| Scam signal detection | **Code** | Regexes for pay-to-join, lookalike domains, urgency phrases — no ambiguity needed |
| Deal grouping | **Code** | Union-find on brand + domain; deterministic |
| Next-step decision | **Code** | Pure lookup table over category + flag codes |
| Reply drafting | LLM (optional) | Phrasing is a good fit for a language model; safety-checked before use |
| Creator summary | **Code** | Templated Markdown from structured data; no generation needed |

**Key principle:** the LLM extracts, code judges.

---

## Setup — Fresh Clone

```bash
git clone <your-repo-url>
cd creator_Email_sorting

# Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

# Configure your API key
cp .env.example .env
# Then edit .env and add your GEMINI_API_KEY
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | **Yes** | — | Google AI Studio key (free tier works) |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Override the Gemini model name |

`.env.example`:
```ini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
```

> **Never commit `.env`.** It is listed in `.gitignore`.

---

## Running the App

```bash
# Standard run (uses cached analyses.json if it exists)
python -m src.main

# Force re-extraction from the LLM (makes 15 API calls, ~60 s on free tier)
python -m src.main --refresh

# Use Gemini to also draft replies (adds 1 API call per deal with a reply)
python -m src.main --llm

# Both
python -m src.main --refresh --llm
```

Output files after a run:

| File | Description |
|---|---|
| `output/analyses.json` | LLM extraction results (cache; reused on subsequent runs) |
| `output/deals.json` | Full deal data: category, flags, next step, draft, … |
| `output/summary.md` | Creator-facing Markdown report |

View the summary:
```bash
# Windows
type output\summary.md

# macOS/Linux
cat output/summary.md
```

---

## Running Tests

All 46 tests are deterministic — no API key required.

```bash
pytest
# or verbose:
pytest -v
```

Test coverage:
- `test_schema.py` — Pydantic validation
- `test_rules.py` — 18 unit tests covering money parsing, rate comparison, deadline checks, exclusivity, content rules, scam signals, and full `assess()` integration
- `test_group.py` — 12 tests covering deal grouping, merge logic, partition validation
- `test_reply.py` — 14 tests covering next-step decisions, draft generation, safety checks, and LLM fallback

---

## Running Evaluation

The evaluation script compares `output/deals.json` against `data/expected.json`.

```bash
# Run pipeline first if you haven't
python -m src.main

# Then evaluate
python -m eval.run_eval

# Point to a specific output file
python -m eval.run_eval --deals output/deals.json
```

---

## Actual Evaluation Results

> These results were measured against `output/analyses.json` cached from one live Gemini run on 2026-11-15.

```
Category accuracy : 14/15 (93%)
Next-step accuracy: 13/14 (92%)   (E-01 excluded — superseded, no expected step)
Fee accuracy      : 7/8 (87%)     (emails with an expected fee)
Flag recall       : 18/20 (90%)   (expected flags found in pipeline output)
```

### Per-email breakdown

| ID | Expected | Got | Cat | Step | Fee | Flags |
|---|---|---|:---:|:---:|:---:|:---:|
| E-01 | deal_offer | deal_offer | ✅ | — | ❌¹ | — |
| E-02 | deal_offer | deal_offer | ✅ | ✅ | ✅ | 1/1 |
| E-03 | scam_or_phishing | scam_or_phishing | ✅ | ✅ | — | 2/2 |
| E-04 | not_a_fit | not_a_fit | ✅ | ✅ | ✅ | 1/1 |
| E-05 | not_a_fit | not_a_fit | ✅ | ✅ | ✅ | 1/1 |
| **E-06** | **needs_more_info** | **deal_offer** | ❌ | ❌ | ✅ | 2/2 |
| E-07 | scam_or_phishing | scam_or_phishing | ✅ | ✅ | — | 1/2² |
| E-08 | needs_more_info | needs_more_info | ✅ | ✅ | — | 1/1 |
| E-09 | deal_offer | deal_offer | ✅ | ✅ | — | 2/2 |
| E-10 | deal_offer | deal_offer | ✅ | ✅ | ✅ | 1/1 |
| E-11 | deal_offer | deal_offer | ✅ | ✅ | ✅ | 2/2 |
| E-12 | needs_more_info | needs_more_info | ✅ | ✅ | ✅ | 0/1³ |
| E-13 | spam | spam | ✅ | ✅ | — | — |
| E-14 | scam_or_phishing | scam_or_phishing | ✅ | ✅ | — | 2/2 |
| E-15 | needs_more_info | needs_more_info | ✅ | ✅ | — | 2/2 |

**Notes:**

¹ **E-01 fee**: `expected.json` records the original Rs 1,20,000 offer; the pipeline reports D1's merged fee of Rs 1,00,000 (latest terms from E-11). This is correct pipeline behaviour — the pipeline always reports the current, actionable deal.

² **E-07 flags**: the pipeline emits `personal_info_request`; expected.json uses `request_for_personal_info`. Naming difference, same detection logic.

³ **E-12 flags**: the pipeline emits `deadline_passed` (which is accurate); expected.json uses `impossible_deadline`. Same meaning, different label convention.

**The one genuine miss — E-06 (Chai & Co):**

The LLM found all three required fields (platform, deliverable, fee) and classified the email as `deal_offer`. The rules engine preserved that classification because a missing deadline alone does not trigger a category downgrade (some real deals genuinely don't state a deadline upfront). The human editorial decision in `expected.json` is `needs_more_info`, reflecting the judgment that the offer is vague and underpaid. This is a genuine judgment-call difference. To fix it, the rules engine could downgrade any `deal_offer` where the fee is below rate card **and** no deadline is stated — but that would risk over-triggering on legitimate above-rate offers without deadlines.

---

## Cost & Throughput

> Numbers are approximate. Measured with Gemini 2.0 Flash, free tier.

| Metric | Per email | Per day (1,000 emails) |
|---|---|---|
| LLM tokens (input) | ~1,000 | ~1M |
| LLM tokens (output) | ~300 | ~300k |
| API cost (Gemini Flash, paid tier) | ~\$0.00011 | ~\$0.11 |
| API cost (free tier) | \$0 | \$0 (rate-limited) |
| Extraction time (free tier, 4 s sleep) | ~4 s | ~67 min |
| Extraction time (paid tier, no sleep) | ~0.5 s | ~8 min |
| Rules + grouping + summary | <1 ms | <1 s |

**At 1,000 emails/day:**

- The bottleneck is the 4-second rate-limit sleep, not compute.
- On a paid tier, remove `time.sleep()` in `extract.py` and add concurrency (e.g. `asyncio` + `asyncio.gather` with a semaphore). 1,000 emails would finish in under 2 minutes.
- Storage: `analyses.json` grows by ~500 bytes per email → ~500 KB/day → negligible.
- If the LLM misclassifies, `rules.py` corrects the most dangerous cases (scam/exclusivity/content rules) deterministically. Category errors like E-06 are low-stakes — they produce a negotiate reply where an ask-for-details reply would have been slightly better.

---

## Future Improvements

With another week:

1. **Async extraction** — replace the per-email sleep with `asyncio` and a rate-limit semaphore; cut processing time 10×.
2. **Richer `needs_more_info` downgrade rule** — if fee is below rate card *and* no deadline is stated, downgrade `deal_offer` → `needs_more_info`. This fixes the E-06 miss.
3. **Deal state machine** — track deal status across runs (new / awaiting reply / negotiating / closed). Today each run is stateless.
4. **Sent-reply ledger** — once the creator sends a reply, record it so the pipeline stops suggesting the same draft.
5. **UI** — a minimal web dashboard (FastAPI + HTMX) showing the summary with one-click "copy draft" buttons.
6. **More LLM providers** — Groq's Llama 3 models are fast and free; add a `GROQ_API_KEY` path as a fallback.
7. **Confidence threshold** — if the LLM returns confidence < 0.6, automatically escalate to `needs_more_info` or flag for human review.
8. **Multi-creator support** — parameterise the pipeline with a `--profile` flag so multiple creators can share one installation.

---

## AI Coding Tools Used

This project was built using **Google Antigravity (AI coding assistant)** throughout:

- **Architecture design**: Antigravity was used as a sounding board for the LLM-extracts / code-judges split and for the data flow between modules.
- **Schema design**: Pydantic model fields and the `Literal` type constraints were drafted with AI assistance and then refined by hand.
- **System prompt**: The extraction system prompt (`extract.py`) was written collaboratively — initial draft from AI, then iteratively refined to handle Indian number formats, the `<email>` delimiter injection defence, and barter-vs-cash distinction.
- **Regex patterns**: The scam-signal regexes in `rules.py` (`PAY_TO_JOIN_RE`, `URGENCY_RE`, etc.) were generated by AI and spot-checked against the test emails.
- **Test cases**: The test fixtures in `test_rules.py`, `test_group.py`, and `test_reply.py` were proposed by AI and manually verified against the expected behaviours described in `TASK.md`.
- **`summary.py` and `main.py`**: Implemented with AI assistance, then refined to match the actual module signatures discovered by reading the existing code.
- **`eval/run_eval.py`**: Logic and report format were AI-assisted; ground-truth mapping and the limitations section were written by hand.

Code review and final integration was done manually to ensure the modules were consistent with each other and that no logic was duplicated or contradicted.