#!/usr/bin/env bash
# Optional external code-review feedback loop (e.g. CodeRabbit, Greptile,
# your own review bot). Disabled by default -- this file is a template, not
# executable, so factory/run_factory.sh skips it until you wire one up.
#
# If you enable a review tool that comments on PRs automatically, make this
# script:
#   1. Poll the PR (via `gh pr view --json comments` or the tool's API) for
#      its review comments/confidence score.
#   2. If feedback exists and isn't yet resolved, re-invoke `claude -p` in
#      the same worktree ($3) on branch $4, telling it to address the
#      specific feedback, then re-run factory/validate.sh, commit, and push.
#   3. Repeat up to a small max round count (e.g. 3), then stop either way
#      so this never loops forever burning API calls.
#
# Usage when enabled: review_loop.sh <issue-number> <pr-url> <worktree-dir> <branch>
#
# Left as a no-op template: `chmod +x` this file and fill it in to activate.
echo "review_loop.sh not configured; skipping external review loop." >&2
exit 0
