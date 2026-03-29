# skills research and portability plan

## Overview

Investigate whether GitHub Copilot CLI's useful skills can be adopted in this repository, whether `DeepResearch` exists as a reusable skill in this environment, and how portable the same skill assets are across GitHub Copilot, Codex, and Claude Code.

Current confirmed findings:

- this repository already uses a project skill at `.agents/skills/twitter-cli/SKILL.md`
- this runtime currently exposes only the `twitter-cli` skill; invoking `deepresearch` failed because it is not installed here
- GitHub Copilot CLI has a built-in `/research` command and a built-in `research` agent, so "deep research" appears to be a built-in agent/workflow in Copilot rather than a missing local `SKILL.md`
- GitHub Copilot CLI officially supports agent skills stored in `.github/skills`, `.agents/skills`, or `.claude/skills`
- GitHub's agent-skills documentation treats `SKILL.md` as a cross-tool format and explicitly supports `.claude/skills` alongside `.github/skills` and `.agents/skills`
- OpenAI Codex officially supports the same `SKILL.md`-based open agent skills standard and scans `.agents/skills`
- Anthropic Claude Code docs confirmed shared `CLAUDE.md`, settings, and MCP across Claude surfaces, but this investigation did not find equally direct Anthropic documentation proving repository skill auto-discovery from the same path conventions

## Questions this plan answers

- Can we "bring in" the previously mentioned DeepResearch capability as a skill in this environment?
- Which useful skills are realistic and high-value for this repository?
- Which parts of a skill are portable across Copilot, Codex, and Claude Code, and which parts are product-specific?
- What is the safest implementation scope to propose to the user next?

## Files / resources involved

- `.agents/skills/twitter-cli/SKILL.md`
  - existing project skill and format reference
- `README.md`
  - documents current skill layout in this repository
- `docs/exec-plans/active/skills-research-and-portability_20260329_0402.md`
  - this execution plan
- Potential new files if implementation is approved:
  - `.agents/skills/research-playbook/SKILL.md`
  - `.agents/skills/github-actions-failure-debugging/SKILL.md`
  - optional supporting `references/` files under each skill directory

## Recommended direction

- Do **not** treat Copilot's DeepResearch as an importable drop-in local skill unless a concrete upstream `SKILL.md` source is identified later
- Treat Copilot DeepResearch as a built-in research workflow (`/research` / built-in `research` agent) that cannot currently be enabled in this API environment just by adding a repository file
- If the user approves implementation, add **portable repository skills** in `.agents/skills/` that capture the most valuable repeatable workflows for this repo and are likely reusable in Copilot and Codex
- Keep the first implementation instruction-only (no helper scripts) unless a script is clearly necessary
- Prefer `.agents/skills/` as the canonical repository location because:
  - this repo already uses it
  - Codex officially scans it
  - Copilot officially supports it
- Note: GitHub's own examples usually use `.github/skills/`; `.agents/skills/` is chosen here for repository continuity and Codex portability rather than because `.github/skills/` is unsupported
- If Claude Code parity becomes important later, verify its exact skill discovery rules separately before adding duplicate `.claude/skills/` wrappers

## Proposed skill candidates

- `research-playbook`
  - use when the task requires a structured investigation across local code, GitHub metadata, and any documentation sources already available in the host runtime
  - intended as the closest practical substitute for the "deep research" workflow in this repo, but it would **not** recreate Copilot's built-in `/research` backend or guarantee web-search capability on every host
- `github-actions-failure-debugging`
  - use when a workflow run or job fails and the agent should follow a consistent investigation sequence
  - especially valuable in this repository because GitHub Actions is central to operations
- `repo-change-planning`
  - use when a multi-file or risky change needs a structured plan, risk notes, and validation checklist before implementation
  - lower priority than the first two, because some of this is already covered by repository instructions and built-in planning modes

## Implementation steps

- [ ] 1. Summarize the research findings for the user, including the distinction between built-in research agents and loadable skills
- [ ] 2. Explain portability clearly: open `SKILL.md` format is shared in principle, but product-specific discovery paths and capabilities still differ
- [ ] 3. Recommend an initial skill set to implement in this repository if the user wants to proceed
- [ ] 4. Ask the user whether to approve implementation, limit the scope, or stop at research only
- [ ] 5. If approved in a later step, implement the selected skills under `.agents/skills/`, validate loading/format, and update directly related documentation only if needed

## Notes / risks

- A locally added skill will not recreate Copilot's built-in `/research` backend behavior; it can only encode a workflow using the tools available in the host agent
- Cross-product portability is strongest at the `SKILL.md` content/spec level, not necessarily at the directory-discovery or UI-command level
- Adding too many skills up front can reduce clarity; a small, high-signal set is safer
- Claude Code compatibility remains the least directly verified part of this investigation, so any "works everywhere" claim should stay conservative until Anthropic-specific skill-loading docs are confirmed
