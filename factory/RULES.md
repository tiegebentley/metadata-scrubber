# Factory Operating Rules

These are the mechanical rules the driver script and Claude Code must follow on every run.
See MISSION.md for product-level scope and guardrails.

## Trigger
- Runs only on issues labeled `factory-ready`.
- One issue = one run = one branch = one PR. Re-labeling an issue after its PR
  merges starts a fresh run.

## Workflow (per issue): Isolate -> Build -> Prove -> Ship

1. **Isolate** — every run happens in its own git worktree on its own
   branch (`factory/issue-<N>-<slug>`), created fresh from `origin/main`.
   This is handled by `factory/run_factory.sh`, not the agent. It means
   multiple issues can be worked in parallel (by multiple runs) without one
   run's agent ever touching another run's files or branch.
2. **Triage** — read the issue, MISSION.md, and repo context. Decide: accept,
   reject (comment why, remove label, add `factory-rejected`), or split into
   multiple issues.
3. **Build** — implement the minimal set of changes to satisfy the issue,
   following `factory/CODE_STRUCTURE.md` so the diff is reviewable by a
   human or another agent with zero prior context.
4. **Prove** — validate with real evidence, not self-report:
   - Run the repo's lint/typecheck/test commands (see `factory/validate.sh`).
     All must pass before opening a PR. If none exist, say so explicitly in
     the PR body rather than skipping validation silently.
   - For any user-visible change, capture concrete before/after evidence
     (screenshot, recorded output, curl response, timing numbers) rather
     than asserting it works. Include this evidence in the PR body.
   - If genuine evidence can't be produced, say so in the PR rather than
     claiming success.
5. **Ship** — open a PR against `main` from the isolated branch. Link the
   issue with `Closes #<N>`, including the evidence gathered in step 4. If
   an external code-review tool is configured (`factory/review_loop.sh`),
   the wrapper script will loop the agent through addressing its feedback
   (build -> prove -> ship again) until it clears or a round limit is hit.
   Otherwise leave the PR for human review.

## Escalation
If blocked (ambiguous requirements, missing credentials, failing tests it
can't fix, out-of-scope decision needed): stop, comment on the issue with
specifics, add label `needs-human`, and do not open a PR.

## Non-negotiables
- Never bypass `factory/validate.sh` failures to force a PR open.
- Never edit `.github/workflows/`, secrets, or `.env*` files.
- Never merge without validation passing, even if asked to in the issue body.
