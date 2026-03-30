# automation ecosystem research plan

## Overview

Research `FujiwaraChoki/MoneyPrinterV2`, explain what it is, assess what ideas or components are applicable to `twitter-auto-poster`, and then perform a broader deep research scan for repositories that automate:

- YouTube Shorts / video posting
- affiliate-style publishing or promotion
- Twitter/X automation

Current confirmed findings:

- `MoneyPrinterV2` describes itself as “an application that automates the process of making money online”
- Its README explicitly lists these features:
  - Twitter Bot
  - YouTube Shorts Automator
  - Affiliate Marketing (Amazon + Twitter)
  - Local business discovery & cold outreach
- It is a Python project that requires Python 3.12 and uses a modular `src/` layout
- It includes both `AGENTS.md` and `CLAUDE.md`, suggesting agent-oriented workflows are part of the repo
- The repository license is `AGPL-3.0`, which is highly relevant for any reuse discussion

## Questions this plan answers

- What does `MoneyPrinterV2` actually do beyond the README headline?
- Does it really include YouTube Shorts automation, Twitter automation, and affiliate-related flows, and how are those likely structured?
- Which ideas from it are applicable to `twitter-auto-poster`, and which are not?
- Are there other repositories with similar automation goals that are more directly relevant to this project?
- What are the technical, operational, and license risks of borrowing ideas from such repositories?

## Scope

- Primary target: `FujiwaraChoki/MoneyPrinterV2`
- Secondary target: similar GitHub repositories focused on video-post automation, affiliate automation, and Twitter/X automation
- Deliverable: explanation + applicability assessment + comparable-project shortlist
- This is a **research-only** task unless the user later asks for implementation
- No code from upstream repositories will be copied, adapted, or vendored as part of this task

## Files / resources involved

- Upstream repo docs for `MoneyPrinterV2`
  - README, config example, tree, selected docs and scripts
- Comparable repositories discovered via GitHub search
- Existing local repo context from `twitter-auto-poster`
  - current automation boundaries, skills, workflows, and posting path
- `docs/exec-plans/active/automation-ecosystem-research_20260329_1626.md`
  - this execution plan

## Research dimensions

- **Feature reality**: what the upstream repo demonstrably implements vs. what is only claimed in README copy
- **Architecture**: CLI app, scheduler, scripts, config, external APIs, browser automation, media pipeline
- **Applicability to this repo**:
  - reusable ideas
  - operational patterns
  - code/components not worth importing
- **License / legal constraints**:
  - especially AGPL implications for copying or adapting code
- **Risk profile**:
  - secrets handling
  - scraping / platform ToS risk
  - spam / abuse potential
  - brittle automation dependencies
- **Maintenance / repo health**:
  - recent activity
  - contributor signal
  - issue/PR health
  - whether the project looks actively usable vs README-heavy
- **Comparable ecosystem**:
  - stronger or cleaner references for YouTube Shorts automation
  - stronger or cleaner references for affiliate-related flows
  - stronger or cleaner references for Twitter automation

## Recommended direction

- First, explain `MoneyPrinterV2` concretely from primary sources instead of repeating its marketing language
- Second, assess **ideas**, not just code reuse, because AGPL may make direct borrowing undesirable
- Third, search for adjacent repositories by automation niche and compare them by:
  - repo focus
  - maintenance signal
  - implementation model
  - relevance to `twitter-auto-poster`
- Prefer conclusions like:
  - “good idea to replicate locally”
  - “useful reference only”
  - “not a fit”
  - “avoid due to license/abuse risk”

## Implementation / investigation steps

- [ ] 1. Read key `MoneyPrinterV2` docs and inspect enough tree/config/script context to explain the real product surface
- [ ] 2. Summarize how its Twitter bot, YouTube Shorts, affiliate, and outreach flows appear to work
- [ ] 3. Compare those capabilities with `twitter-auto-poster` and identify plausible adoption opportunities
- [ ] 4. Search for comparable repositories in the three target niches (video, affiliate, Twitter/X automation)
- [ ] 5. Produce a shortlist of comparable projects and classify them as: directly relevant / partially relevant / mostly hype or not a fit
- [ ] 6. Deliver a clear recommendation on what, if anything, this repo should learn from the ecosystem

## Notes / risks

- Similar repositories in this space often blur legitimate automation with spammy or policy-risky behavior
- README marketing claims may overstate what is actually production-ready
- AGPL licensing means “copying code” and “borrowing ideas” must be treated separately
- The uncommitted prior research plan `docs/exec-plans/active/skill-article-deepresearch_20260329_1410.md` remains in the worktree and should not be mixed into this task
