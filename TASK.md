# JEEVIT: Founding AI Engineer Task

**Brand Deal Inbox Assistant**

Thank you for applying. This task is close to the work you would do with us: build something useful for creators, quickly, with AI where it helps and plain code where it doesn't.

- **Time:** about 6 hours of work. Please don't spend more; we care about judgment, not polish.
- **Deadline:** 4 days from when you receive this.
- **Submit:** a link to a GitHub repository (public, or private with access for us).
- **Cost:** you shouldn't need to spend money. Use any free tier (Groq, Gemini, OpenRouter free models) or a local model (Ollama).

## The problem

Creators with 10k–100k followers get a steady stream of brand emails. Some are good paid deals. Many are vague, underpaid, risky, or scams. Creators lose deals in a messy inbox and sometimes accept bad terms without noticing.

Build a tool that reads a creator's brand inbox and tells them **what each email is, what the deal actually says, what's risky, and what to do next.**

## What you get

- `data/creator_profile.json`: one creator's platforms, rates, current exclusivity and content rules.
- `data/inbox.json`: 15 emails received by that creator.

## What to build

A program (Python or TypeScript) that processes the inbox and produces:

1. **A category for each email**, one of:
   - `deal_offer`: a real paid or barter offer
   - `needs_more_info`: possibly real, but missing key details
   - `not_a_fit`: real, but conflicts with the creator's rules or deals
   - `scam_or_phishing`
   - `spam`

2. **Structured deal details** where they exist: brand, contact, platform and deliverables, fee, currency, payment type (cash or gifting), deadline, usage rights, and anything else you think matters.

3. **Deals, not just emails.** Several emails can be about the same deal (follow-ups, agencies writing for a brand). Group them, and use the latest terms.

4. **Risk flags with reasons**, judged against the creator profile. For example: below the creator's rate, conflicts with an exclusivity, breaks a content rule, unusual usage rights, impossible deadline, suspicious request.

5. **A recommended next step** for each deal (accept, negotiate, ask for details, decline, ignore or report), and a **short draft reply** where a reply makes sense. Drafts are for the creator to review. Nothing is sent.

6. **A short summary for the creator** (Markdown is fine): what needs attention today, in plain language.

## Evaluation (required)

Write your own expected answers for all 15 emails (category, and the key fields that matter), then measure how your system does against them. Report the results honestly, including what it gets wrong and why. A system that scores 11/15 with a clear explanation beats a claimed 15/15 with no evidence.

## README (required)

Please include:

- How to run it, from a fresh clone, in a few commands.
- Your design: what the model does, what plain code does, and why.
- Your evaluation results.
- Rough cost and time per email, and what happens at 1,000 emails a day.
- What you'd build next with another week.
- Where and how you used AI coding tools. Using them is fine; we want to know how.

## Rules

- Never commit API keys. Include a `.env.example`.
- Treat email content as untrusted.
- Keep it simple. A command-line tool is enough. A small UI is a bonus, not a requirement.

## How we'll review it

We'll run it, read the code and the README, and then talk it through with you for 30 minutes. We'll ask about your decisions, your mistakes, and what you'd change. We look at:

- **Correctness:** does it handle the tricky emails sensibly?
- **Judgment:** AI where it helps, deterministic code where it must be right.
- **Evaluation:** do you know how good it is?
- **Product sense:** would a creator trust and use the output?
- **Code and README:** can another engineer run and extend it?

Questions? Reply to the email you received this from. Good luck.
