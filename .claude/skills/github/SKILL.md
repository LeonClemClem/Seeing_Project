---
name: github
description: How we collaborate on this repository with git and GitHub. Use whenever code is about to be changed, committed, pushed or reviewed — every piece of work happens on its own branch with a pull request, meaningful commit messages, and a PR description kept up to date.
---

# Working together on GitHub

Repository: https://github.com/LeonClemClem/Seeing_Project — `main` is protected by convention:
nobody commits to it directly. Changes reach `main` only through a reviewed pull request.

## 1. Start from an up-to-date `main`, on a new branch

```bash
git switch main
git pull --ff-only
git switch -c <type>/<short-topic>
```

- One branch per topic (a fix, a feature, a refactor). Do not mix unrelated changes.
- Branch names: `feat/...`, `fix/...`, `refactor/...`, `docs/...`, `chore/...`,
  e.g. `feat/fisheye-5deg`, `fix/copernic-collector-timezone`.
- If the work continues an open PR, check out that PR's branch instead of creating a new one.
- Before starting, `git status` must be clean. Never discard someone else's uncommitted work.

## 2. Commit in small, meaningful steps

Each commit is one logical change that leaves the code working. Message format:

```
<area>: <what changed, imperative, <= 72 chars>

Why the change was needed and anything a reviewer should know
(behaviour changes, new parameters, data or cache impact, how it was tested).
```

- `<area>` is the part of the repo: `research`, `web`, `api`, `infra`, `skills`, ...
- Good: `research: read data folders from chemins.py instead of absolute paths`
- Bad: `update`, `fix`, `wip`, `Add files via upload`.
- Stage files explicitly (`git add <paths>`), and review `git diff --staged` before committing.
- Never commit data or machine-specific files: GRIB files, caches, figures, measurement CSVs,
  `research/chemins_locaux.json`, logs, credentials. `.gitignore` covers them; check anyway.

## 3. Check before pushing

Run the `red-team` skill (fast review agent) on the branch before the first push and before
asking for a merge. Fix what it reports, or explain in the PR why it is acceptable.

## 4. Push and open (or update) the pull request

```bash
git push -u origin <branch>
gh pr create --base main --fill   # if the GitHub CLI is installed
```

Without `gh`, open `https://github.com/LeonClemClem/Seeing_Project/compare/main...<branch>`.

The PR description has these sections and is **updated after every push**, not only at creation:

```markdown
## Summary
What this PR does and why, in 2-4 sentences.

## Changes
- Bullet per logical change (mirror the commits).

## How it was tested
Commands run, figures compared, what was NOT tested.

## Notes for the reviewer
Data/cache impact, follow-ups, open questions.
```

With `gh`: `gh pr edit <number> --body-file <file>`. Without it, edit the description on GitHub.

## 5. Review and merge

- The other person reviews; the author answers comments with new commits (no force-push on a
  branch someone else is reviewing, unless agreed).
- Merge only when the PR is green and approved. Prefer "Squash and merge" for small PRs.
- After merge: `git switch main && git pull --ff-only` and delete the branch.

## Rules for Claude

- Never push, merge, force-push, delete a branch or edit a PR without the user's explicit OK
  in the conversation. Show the commit list and the diff summary first.
- Never commit as the user with their personal e-mail: the repo uses
  `LeonClemClem@users.noreply.github.com` as author address.
- Never put credentials in commands, URLs or files. Authentication is done by the user in the
  Git Credential Manager window.
