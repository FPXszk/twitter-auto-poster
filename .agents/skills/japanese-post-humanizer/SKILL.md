---
name: japanese-post-humanizer
description: Anti-AI writing rules for Japanese X/Twitter posts. Invoke when drafting, reviewing, or polishing Japanese social media text to ensure it reads like natural human writing rather than LLM output.
---

# japanese-post-humanizer — Natural Japanese Post Polishing

Apply these rules whenever producing or reviewing Japanese text destined for X (Twitter) posts in this repository.

## When to Use

- Drafting a new Japanese post or summary
- Reviewing Copilot-generated Japanese output before publishing
- Editing `config/copilot_summary_prompt_ja.txt` or `config/copilot_reply_prompt_ja.txt`

## Hard Constraints (never override)

These come from the repository's posting pipeline and must always be respected:

1. **No invented facts** — never add information absent from the source
2. **Preserve names and numbers** — keep important proper nouns, figures, and entities
3. **280 characters max** — strict limit for a single X post
4. **No URLs, @mentions, or hashtags** in generated body text
5. **One natural paragraph** — no line breaks, bullet points, or headings
6. **Body only** — no preamble or postscript

## Anti-AI Japanese Rules

### Expressions to avoid (unless present in the source)

| Pattern | Why it sounds AI-generated |
|---|---|
| 〜と言えるでしょう | Commentary/pundit tone rare in casual posts |
| 〜が注目されます / 〜が期待されます | Passive-voice hedging typical of LLM output |
| 重要 / 注目 / 画期的 / 革新的 | Over-dramatic modifiers added by models |
| つまり / すなわち / 要するに (as openers) | Summarizing markers that signal machine rewrite |
| 〜について解説します / 〜をご紹介します | Presenter/explainer framing |

### Structural habits to avoid

- **Stacked noun-stop sentences (体言止め連続)** — e.g. 「新機能。高速化。低コスト。」 Sounds like a bullet list rewritten into a paragraph.
- **Unnatural inversion (不自然な倒置)** — keep standard Japanese word order.
- **Overly balanced parallel clauses** — real tweets are slightly messy; perfect symmetry is a tell.

### Positive guidance

- **Match the source tone** — if the original is casual, stay casual; if it is serious, stay serious.
- **Prefer concrete verbs** over abstract nominalizations (e.g. 「発表した」 over 「発表が行われた」).
- **Use colloquial endings where appropriate** — 「〜だ」「〜した」「〜らしい」 instead of always 「〜です」「〜ました」.
- **Allow minor roughness** — a slightly unpolished sentence reads more human than a perfectly balanced one.

## Quick Self-Check

Before finalizing Japanese post text, verify:

1. ≤ 280 characters?
2. Would a real person actually tweet this phrasing?
3. Are there any evaluative words not in the source?
4. Does the sentence structure feel natural when read aloud?
