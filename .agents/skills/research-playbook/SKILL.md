---
name: research-playbook
description: Structured research workflow for investigating codebases, bugs, and technical questions. Encodes a repeatable playbook using whatever tools the host runtime provides — not a replacement for built-in research commands.
---

# research-playbook — Structured Research Workflow

This skill encodes a **repeatable research playbook** that any AI agent can follow using the tools available in its runtime (grep, glob, file viewers, web fetch, code search, etc.). It does not replace or recreate any built-in research command; instead it provides a disciplined process for conducting investigations.

## When to Use

- Investigating an unfamiliar area of the codebase
- Diagnosing a bug whose root cause is unclear
- Answering a technical question that requires evidence from multiple sources
- Preparing context before implementing a change

## Research Workflow

### Phase 1: Frame the Question

Before searching anything, write down:

1. **Goal** — one sentence describing what you need to learn
2. **Scope** — which files, modules, or systems are likely relevant
3. **Success criteria** — what constitutes a sufficient answer

If the task is about product behavior or compatibility, explicitly separate:

- built-in features
- loadable skills/plugins/agents
- repository-specific conventions

### Phase 2: Broad Discovery

Gather structural context first. Prefer fast, broad tools:

```text
1. Directory listing / tree of relevant modules
2. Glob for file patterns (e.g., **/*.yml, **/*test*)
3. Grep for key identifiers (function names, error messages, config keys)
4. README / doc files in the target area
```

**Tips:**
- Batch independent searches — run multiple grep/glob calls in parallel
- Prefer `files_with_matches` mode before reading full content
- Note file paths and line numbers for later deep-dives

### Phase 3: Targeted Deep-Dive

Once you have candidate files, read the specific sections:

```text
1. View relevant file ranges (not whole files unless small)
2. Trace call chains: caller → function → dependencies
3. Check tests for behavioral documentation
4. Look at recent git history for the area (git log --oneline -10 -- <path>)
```

**Tips:**
- Follow imports/requires to understand data flow
- Check config files that control the behavior under investigation
- Read test assertions — they encode expected behavior

### Phase 4: Cross-Reference

Validate findings against multiple sources:

```text
1. Do official docs match the code and local behavior?
2. Do the tests match the implementation?
3. Are there related issues, PRs, or comments?
4. Is the behavior consistent across environments (local vs CI)?
```

### Phase 5: Synthesize and Report

Produce a concise summary:

```text
1. Answer to the original question (1–3 sentences)
2. Key evidence (file paths, line numbers, relevant snippets)
3. Confidence level (high / medium / low) and any remaining unknowns
4. Recommended next steps if the answer is incomplete
```

## Anti-Patterns to Avoid

| Anti-Pattern | Better Approach |
|---|---|
| Reading entire large files before knowing what to look for | Grep first, then view specific ranges |
| Sequential single-query searches | Batch parallel searches |
| Stopping after first plausible answer | Cross-reference with tests and docs |
| Ignoring git history | Check `git log` and `git blame` for context |
| Researching without a clear question | Frame the question before searching |

## Adapting to Different Runtimes

This playbook is tool-agnostic. Map the abstract steps to whatever is available:

| Abstract Step | Example Tools |
|---|---|
| Directory listing | `view <dir>`, `tree`, `ls` |
| Pattern search | `grep`, `rg`, code search MCP |
| File reading | `view`, `cat`, `github-mcp-server-get_file_contents` |
| Git history | `git log`, `git blame`, `github-mcp-server-list_commits` |
| Web/docs lookup | `web_fetch`, GitHub docs search |
| Parallel execution | Multiple tool calls in one response, explore agents |
