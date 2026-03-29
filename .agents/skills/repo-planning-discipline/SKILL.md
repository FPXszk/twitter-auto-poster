---
name: repo-planning-discipline
description: Reinforces this repository's planning workflow — when to use exec-plans vs session plan.md vs SQL todos, and a pre-implementation completeness checklist. Invoke when starting a new task or reviewing a plan before implementation.
---

# repo-planning-discipline — Planning Workflow for This Repository

This skill encodes the operational planning discipline specific to this repository. It complements the always-on rules in `.github/copilot-instructions.md` by providing concrete decision guidance and a completeness checklist.

## When to Use

- Starting any non-trivial task (more than a single-file edit)
- Deciding where to record a plan
- Reviewing a plan before asking the user for approval
- Choosing between markdown prose and SQL tracking

## Planning Artifacts — When to Use What

| Artifact | Location | Use When |
|---|---|---|
| **Committed exec-plan** | `docs/exec-plans/active/<name>_YYYYMMDD_HHMM.md` | Multi-step implementation that needs user review before starting. Move it to `completed/` when entering the COMMIT step. |
| **Session plan.md** | Session workspace (e.g. `~/.copilot/session-state/plan.md`) | Ephemeral working notes for the current session — approach ideas, scratch analysis, intermediate findings. Not committed. |
| **SQL todos** | Session SQLite `todos` table | Tracking individual implementation steps within an approved plan — status (`pending`/`in_progress`/`done`/`blocked`), dependencies, and batch progress. |

### Decision Flow

```
Is this a throwaway note or scratch analysis?
  → session plan.md

Is this a durable, reviewable implementation plan?
  → docs/exec-plans/active/

Do I need to track step-by-step progress with status?
  → SQL todos (backed by the approved exec-plan)
```

## Pre-Implementation Completeness Checklist

Before asking the user to approve a plan, verify every item:

- [ ] **Files listed** — every file to create, modify, or delete is explicitly named
- [ ] **Scope bounded** — out-of-scope items are stated so the reviewer knows what is intentionally excluded
- [ ] **Test strategy stated** — which tests will be added or extended, and what the RED/GREEN/REFACTOR sequence looks like
- [ ] **Validation commands identified** — which existing repo commands will be run after implementation (e.g. `python3 -m unittest discover -s tests`)
- [ ] **Risks noted** — anything that could go wrong or needs watching
- [ ] **No overlap with existing plans** — check `docs/exec-plans/active/` for conflicting in-flight work

## Workflow Sequence (Quick Reference)

1. **PLAN** — Write exec-plan → sub-agent review → save to `docs/exec-plans/active/` → ask user
2. **IMPLEMENT** — Follow approved plan → TDD (RED → GREEN → REFACTOR) → sub-agent quality check
3. **REVIEW** — Sub-agent code review → ask user
4. **COMMIT** — Move plan to `completed/` → commit and push → ask user
5. **WAIT** — Await next instruction

## Anti-Patterns

| Anti-Pattern | Correct Approach |
|---|---|
| Starting code before plan approval | Always wait for explicit user approval after PLAN step |
| Tracking steps only in prose | Use SQL todos for step-by-step status when plan has 3+ steps |
| Committing session plan.md | Session artifacts stay local; only exec-plans are committed |
| Creating root-level planning files | Use `docs/exec-plans/` — no planning files in the repository root |
| Duplicating copilot-instructions.md | This skill adds operational guidance, not a copy of the constitution |
