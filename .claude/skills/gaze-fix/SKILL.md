---
name: gaze-fix
description: Apply the top suggestion from a gaze-review to a code repository and prove it with numbers. Proposes a minimal diff, waits for explicit approval, applies it on a new git branch without committing, re-runs gazemap on the local dev server, and produces side-by-side before and after overlays with the change in the target's attention share. Use when asked to fix, apply, or verify an attention review suggestion.
user-invokable: true
args:
  - name: url
    description: The page on the local dev server to fix and measure, for example http://localhost:3000/
    required: true
  - name: repo
    description: Path to the repository that serves that page
    required: true
---

You are turning one suggestion from `review.md` into a verified change. The measure of success is the target's attention share before and after, from gazemap, on the same dev server, with the same flags. Nothing in the repository changes before the user says yes, and nothing gets committed.

## Where things are

Run gazemap commands from its checkout: `$GAZEMAP_HOME` if set, else the current directory if it contains `src/gazemap`, else `~/Documents/projects/gazemap` if it exists, else ask. Working directories for this skill live there under `compare/`. The repository is the second argument; every `git` and file edit happens there.

## Steps, in order

1. **Find the spec.** Prefer a measured redesign: if `compare/improve/<page-slug>/best.css` and its `improve.md` exist, the change to port is that stylesheet, translated into the repository's own components and styles, and the targets come from `improve.md`. Otherwise look for `runs/<page-slug>/review.md`; if there is none, list `runs/*/review.md` and ask which page it is for. From the review take the target selector(s) from the Goal line, the hidden selector from the "Captured" line if any, and the first suggestion unless the user named another. If neither exists, say so and offer `/gaze-review` or `/gaze-improve` first; do not invent a target.
2. **Preflight the repository.** `git -C <repo> status --porcelain` must be empty and `git -C <repo> branch --show-current` must not be a detached head. A dirty tree stops the run: ask the user to commit or stash first. Never branch over uncommitted work.
3. **Baseline on the dev server.** Run
   `uv run gazemap analyze <url> --viewport both --top 8 [--hide "<selector>"] --target "<selector>" ... --no-report --out compare/before`.
   Exit code 2 means the server is not running: quote the error, point at the repository's own way to start it (README, `package.json` scripts, `.claude/launch.json`), and stop. Do not start servers yourself unless the user asks. Never use the live site as the baseline; the after run must hit the same server as the before run.
4. **Locate the code.** Search the repository for the element: the id or classes from the target selector, the visible text from `hotspots.json`, the component name. Read the file. Draft the smallest diff that implements the suggestion: markup and styles, no logic changes, no refactors, no new dependencies. Follow the repository's conventions for where styles live.
5. **Propose and stop.** Show the diff as a unified diff, one paragraph on what it changes and why it should move the target's share (cite the hotspot rank, element, and share from the review), and the expected effect. Then ask for approval with AskUserQuestion when it exists (options: apply, change it, use the next suggestion instead), otherwise ask in chat. Apply nothing until the answer is an explicit yes. "Looks good" is not yes; ask again.
6. **Branch and apply.** `git -C <repo> checkout -b gaze-fix/<short-kebab-name>`, then make the edit with the file editing tool. Do not commit, stage, or push. If the dev server hot-reloads, wait a few seconds and use `--wait 2000` on the next run; if it needs a rebuild, tell the user what to run and wait for them to confirm before measuring.
7. **After run.** The same gazemap command as step 3 with `--out compare/after`.
8. **Compare.** `uv run gazemap compare compare/before/<dev-slug> compare/after/<dev-slug> --out compare/<dev-slug>`. This writes `<viewport>.png` side-by-side overlays with the target boxes marked and `compare.json` with the deltas. Read the images.
9. **Write `fix.md`** in `compare/<dev-slug>/` using `fix-template.md` next to this file, and copy it to `~/Desktop/gazemap-reports/<dev-slug>-fix.md`.
10. **Report in chat.** The before, after, and delta for each target per viewport, a sentence on what the side-by-side shows, the branch name and changed files, the path of `fix.md`, and the three options: keep the branch (the user commits), revert (`git -C <repo> checkout -- <files>` then `git -C <repo> checkout <previous-branch>` and `git -C <repo> branch -D <branch>`), or try the next suggestion on the same branch.

## Judging the result

- The target's share went up by a meaningful amount on the viewport the suggestion addressed: call it a fix. State the numbers; do not oversell a fraction of a point.
- No change or a drop: say so plainly. Do not tweak the diff repeatedly hoping for a better number; offer the next suggestion or a revert.
- A change that helps one viewport and hurts the other is a trade-off, not a fix. Show both.
- Page height or layout changes move everything, so also report the top hotspots before and after, not only the target.

## Rules

- No commits, no pushes, no changes outside the branch. One suggestion per run.
- No edits before an explicit yes. No edits at all if the tree was dirty.
- Same server, same flags, same targets on both sides of the comparison.
- Plain Markdown in `fix.md`, no em dashes, no dates in the file.
- The model caveat from the review still applies; the delta is a prediction, not a measurement of users.
