---
name: project-status
description: Orientation for the Seeing AROME monorepo and upkeep of docs/summary.md — what each part does, how it is deployed on GCP, recent work and the roadmap. Use when starting any task in this repo, when asked about architecture, deployment, recent work, priorities or "what's next", or when asked to summarize or update the project status.
---

# Project status

The project summary lives in `docs/summary.md`: repo map, GCP runtime, local dev commands, gotchas, recent work and roadmap. It links to `docs/architecture.md` and `infra/terraform/README.md` instead of repeating them.

## Getting oriented

Read `docs/summary.md` first. Check its **As of commit** line against `git log --oneline -1`; if work has landed since, skim `git log --oneline <that commit>..HEAD` before trusting the "Recent work" and "Roadmap" sections.

## Regenerating the summary

Do this when you finish significant work, or when the user asks to summarize or refresh the status.

1. Collect what changed since the commit in the header:
   - `git log --oneline --no-merges <as-of commit>..HEAD`
   - `git diff --stat <as-of commit>..HEAD`
   - any new or changed README, `docs/` or runbook files.
2. Update `docs/summary.md` in place:
   - Add entries to **Recent work**, newest last, with absolute dates (YYYY-MM-DD) and short commit hashes.
   - Move finished items out of **Roadmap**, and add newly discovered work.
   - Fix the **Repo map**, **Runtime on GCP**, **Local dev** and **Gotchas** sections if the code or infra changed.
   - Keep links to existing docs rather than copying their content.
3. Rewrite the header:
   - **Author:** the git identity of the person driving the work (`git log -1 --format='%an'`), followed by "(generated with <model> via the `project-status` skill)".
   - **Last updated:** the current UTC time from `date -u +%Y-%m-%dT%H:%M:%SZ`.
   - **As of commit:** the short hash and branch the summary describes.
4. Commit `docs/summary.md` with the work it describes, or on its own with a message like "docs: refresh project summary".
