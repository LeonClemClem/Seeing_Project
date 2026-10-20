---
name: red-team
description: Fast adversarial review of the current branch before pushing or merging — checks that the code runs and that nothing unsafe is committed (passwords, tokens, personal data, machine paths, large data files). Use before every push, before asking for a merge, or when the user says "red team" / "check before push".
---

# Red team review

Delegate the review to the **`red-team` agent** (`.claude/agents/red-team.md`), which runs on a
fast Claude model (Haiku). Launch it with the Agent tool, `subagent_type: "red-team"`, and give it:

- the branch name and the base (`main`),
- the list of changed files (`git diff --name-only main...HEAD` plus staged and unstaged files),
- what the change is supposed to do, and how to run the affected scripts
  (Python: `C:\Users\clement\.conda\envs\py313_env\python.exe` on the user's PC, or `poetry run`).

Wait for its report, then:

1. Show the user the findings, most severe first.
2. **Blocking** findings (secret, credential, personal data, data file, broken script) must be
   fixed before any push. If a secret was already committed, do not just delete it in a new
   commit: tell the user it must be rotated, and that history must be cleaned before pushing.
3. Non-blocking findings go into the PR description under "Notes for the reviewer" or are fixed.
4. Never push on the strength of the review alone: the user still confirms the push
   (see the `github` skill).
