# Creator Email Sorting

An automated pipeline for extracting, evaluating risk, grouping deals, drafting responses, and summarizing incoming sponsorship/business emails for creators.

## Folder Layout

```text
data/
  expected.json       # Given files and evaluation benchmarks
src/
  schema.py           # Pydantic data models
  llm.py              # LLM interface: call_llm(prompt) -> json
  extract.py          # Per-email LLM extraction
  rules.py            # Deterministic risk checks
  group.py            # Deal grouping
  reply.py            # Next step recommendations + draft generation
  summary.py          # Creator summary dashboard
  main.py             # Pipeline execution entry point
eval/
  run_eval.py         # Evaluation benchmark runner
tests/
  test_rules.py       # Unit tests for deterministic risk checks
.env.example          # Environment variables template
.gitignore            # Git ignore rules
README.md             # Project documentation
```

## Setup & Usage

1. Copy `.env.example` to `.env` and fill in your API credentials:
   ```bash
   cp .env.example .env
   ```
2. Run the main pipeline:
   ```bash
   python -m src.main
   ```
3. Run evaluation:
   ```bash
   python -m eval.run_eval
   ```
4. Run tests:
   ```bash
   pytest
   ```

## Triage Decisions & Justifications (E-06, E-09, E-12)

This section details the classification taxonomy, policy enforcement rules, and edge-case justifications encoded in `data/expected.json` based on Riya Menon's creator profile (`data/creator_profile.json`).

### 1. Edge-Case Decisions (E-06, E-09, E-12)

- **E-06 (Chai & Co)**: Classified as `needs_more_info` because although ₹25k for 1 reel is proposed, key commercial terms (timeline, usage rights, product scope) are absent and the fee falls below the ₹40k rate card, requiring scope clarification and polite rate alignment in Hinglish.
- **E-09 (BrewBox)**: Classified as `deal_offer` (barter) with a recommendation to decline or counter with standard rates, because a ₹3,500 product gift is heavily disproportionate to ₹60,000 worth of requested deliverables (1 reel + 2 stories).
- **E-12 (SnapMeal)**: Classified as `needs_more_info` because the ₹45,000 budget exceeds Riya's ₹40,000 rate card and an email received on 10 November citing a 1 November deadline is almost certainly a typographical error (e.g., intended for 1 December or post-Diwali) that should be clarified before forfeiting a viable paid deal.

