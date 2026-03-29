# humanizer and planning application plan

## Overview

Apply the two highest-value ideas from the previous skill research to this repository:

- `humanizer-ja`
- `planning-with-files`

This should be done in a repository-native way rather than by blindly importing upstream behavior.

Current confirmed findings:

- The Japanese post generation path already uses `config/copilot_summary_prompt_ja.txt` via `summary_prompt_path` in `config/accounts.yaml`
- `scripts/lib/copilot_summary.py` simply loads the configured prompt template and injects `{source_text}`, so prompt-level changes can directly influence output quality without changing runtime behavior
- The current summary prompt strongly enforces factual accuracy and 280-character output, but it does not yet encode explicit anti-AI-writing heuristics inspired by `humanizer-ja`
- This repository already enforces a planning workflow through `.github/copilot-instructions.md`, session `plan.md`, SQL todos, and committed `docs/exec-plans/active|completed/`
- There is no existing repository hook configuration under `.github/`, so copying `planning-with-files` as-is would likely add a second planning system rather than strengthen the current one
- The repository already has repo-local skills under `.agents/skills/`, so adding one more focused skill is consistent with current structure

## Goal

Improve Japanese output quality and planning discipline **without** introducing overlapping workflows, unnecessary tooling, or host-specific complexity.

## Files likely involved

- `config/copilot_summary_prompt_ja.txt`
  - integrate the highest-value `humanizer-ja` guidance while preserving factual and length constraints
- `.agents/skills/`
  - add one or more repo-local skills tailored to this repository's preferred workflow
- `README.md`
  - update skill tree only if a new repo-local skill is added
- `tests/test_copilot_summary.py`
  - extend prompt/template validation where useful
- `tests/`
  - add a small skill metadata validation test if new skills are added
- `docs/exec-plans/active/humanizer-and-planning-application_20260329_1517.md`
  - this execution plan

## Recommended implementation direction

### 1. Apply `humanizer-ja` in two layers

- **Primary application:** refine `config/copilot_summary_prompt_ja.txt`
  - keep the existing accuracy and 280-character rules as the hard constraints
  - add a small, explicit set of anti-AI-Japanese heuristics inspired by `humanizer-ja`
  - prefer concrete natural wording over abstract or over-formal phrasing
  - avoid bloated stock expressions unless they are present in the source
- **Secondary application:** add a repo-local reusable skill
  - likely path: `.agents/skills/japanese-humanizer/SKILL.md`
  - scope it as a general Japanese post-polishing skill for this repo's writing tasks
  - keep it instruction-only and lightweight

### 2. Apply `planning-with-files` as a repository-native adaptation, not a direct import

- Do **not** introduce the upstream root-level `task_plan.md` / `findings.md` / `progress.md` workflow directly
- Do **not** add hooks or lifecycle automation unless absolutely necessary
- Instead, add a focused repo-local skill that reinforces the existing planning system:
  - use `docs/exec-plans/active/` for committed implementation plans
  - use session `plan.md` for local active context
  - use SQL todos for status tracking
  - explicitly avoid starting implementation before a reviewed plan and user approval
  - add value beyond existing always-on instructions by providing a compact operational checklist for:
    - when to use committed exec-plans vs session `plan.md`
    - when to track state in SQL vs prose in markdown
    - how to do a quick pre-implementation completeness check before asking the user for approval
- likely path: `.agents/skills/repo-planning-discipline/SKILL.md`

## Why this direction is safer

- It reuses the repository's current conventions instead of creating two competing planning systems
- It keeps `humanizer-ja` close to the actual summary path where quality matters most
- It avoids dependence on hooks, plugin marketplaces, or host-specific install flows
- It keeps portability reasonable because the new skills stay plain `SKILL.md` files under the existing repo layout

## Test and validation strategy

- **RED**
  - add or extend tests before changing behavior:
    - prompt-template sanity test(s) for required placeholder and expected constraints
    - lightweight skill file validation test(s) if new skills are added (for example: file presence, non-empty body, expected title/sections)
- **GREEN**
  - make the minimal prompt and skill changes needed
- **REFACTOR**
  - tighten wording for clarity without broadening scope
- validate with the repository's existing commands relevant to these files:
  - `python3 -m unittest discover -s tests`
  - `python3 -m py_compile python/*.py scripts/lib/*.py`
  - YAML validation if any related config is touched
  - `git diff --check`

## Scope boundaries

- In scope:
  - prompt refinement for Japanese summary quality
  - one or two repo-local skills tailored to this repository
  - tests directly related to the prompt/skill additions
  - README update only if the skill tree changes
- Out of scope:
  - plugin marketplace installation
  - `.github/hooks/` or external hook automation
  - replacing the repository's existing planning workflow
  - changing summary provider logic

## Implementation steps

- [ ] 1. Add failing tests for the new prompt/skill expectations
- [ ] 2. Refine `config/copilot_summary_prompt_ja.txt` with a small `humanizer-ja`-inspired rule set
- [ ] 3. Add a repo-local Japanese polishing skill under `.agents/skills/`
- [ ] 4. Add a repo-local planning-discipline skill adapted to `docs/exec-plans`, session `plan.md`, and SQL todos
- [ ] 5. Update README skill tree if needed
- [ ] 6. Run repository validation commands and review the changes

## Risks / watch-outs

- Over-tuning the prompt could reduce fidelity to the source tweet if the anti-AI wording rules are too aggressive
- A planning skill that merely duplicates repository instructions would add noise instead of value
- Skill names should remain specific and repository-appropriate, not generic copies of upstream branding
- The uncommitted plan file `docs/exec-plans/active/skill-article-deepresearch_20260329_1410.md` exists from the previous research step and should not be accidentally mixed into this implementation work
