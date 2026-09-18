#!/usr/bin/env bash
# Drives one factory cycle for a single GitHub issue using headless Claude Code.
#
# Usage: factory/run_factory.sh <issue-number>
#
# Requires: gh (authenticated), claude (Claude Code CLI, authenticated),
# jq. Run from the root of the target repo.
set -euo pipefail

ISSUE_NUMBER="${1:?usage: run_factory.sh <issue-number>}"
REPO_ROOT="$(git rev-parse --show-toplevel)"
FACTORY_DIR="$REPO_ROOT/factory"
WORKTREE_ROOT="${FACTORY_WORKTREE_ROOT:-$REPO_ROOT/.factory-worktrees}"
LABEL_READY="factory-ready"
LABEL_NEEDS_HUMAN="needs-human"
LABEL_REJECTED="factory-rejected"

cd "$REPO_ROOT"

issue_json="$(gh issue view "$ISSUE_NUMBER" --json title,body,labels)"
issue_title="$(echo "$issue_json" | jq -r .title)"
issue_body="$(echo "$issue_json" | jq -r .body)"
labels="$(echo "$issue_json" | jq -r '.labels[].name' | tr '\n' ',')"

if [[ "$labels" != *"$LABEL_READY"* ]]; then
  echo "Issue #$ISSUE_NUMBER is not labeled '$LABEL_READY'; skipping." >&2
  exit 0
fi

slug="$(echo "$issue_title" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-\|-$//g' | cut -c1-40)"
branch="factory/issue-${ISSUE_NUMBER}-${slug}"

# Isolation: each issue gets its own git worktree on its own branch, so
# multiple factory runs (parallel issues, parallel agents) never share a
# working directory or collide on uncommitted state. See RULES.md "Isolate".
mkdir -p "$WORKTREE_ROOT"
worktree_dir="$WORKTREE_ROOT/issue-${ISSUE_NUMBER}-${slug}"

git fetch origin main
git worktree remove --force "$worktree_dir" 2>/dev/null || true
rm -rf "$worktree_dir"  # ensure a clean slate if the remove failed (stale dir from a crash)
git branch -D "$branch" 2>/dev/null || true
git worktree add -B "$branch" "$worktree_dir" origin/main

cleanup_worktree() {
  cd "$REPO_ROOT"
  git worktree remove --force "$worktree_dir" 2>/dev/null || true
}
trap cleanup_worktree EXIT

cd "$worktree_dir"
wt_factory_dir="$worktree_dir/factory"
pr_draft="$wt_factory_dir/.pr_draft.md"
escalation="$wt_factory_dir/.escalation.md"

prompt_file="$(mktemp)"
cat > "$prompt_file" <<EOF
You are operating as an autonomous AI software factory worker, running in
an isolated git worktree on branch $branch. You will never work directly
on main, and this worktree is not shared with any other concurrent run.

Read and strictly follow, in this order:
- factory/MISSION.md (product scope and guardrails)
- factory/RULES.md (operating rules for this run)
- factory/CODE_STRUCTURE.md (how to write the code itself)

You are handling GitHub issue #$ISSUE_NUMBER in this repo:

Title: $issue_title

Body:
$issue_body

Do the full triage -> plan -> build -> prove cycle described in RULES.md.

BUILD: Follow factory/CODE_STRUCTURE.md. Match existing repo conventions.
Keep the change scoped to this issue only.

PROVE (evidence-driven): You must not simply assert the work is done.
Gather concrete evidence before claiming success:
- If there's a UI surface: capture a before state and an after state
  (e.g. a Playwright screenshot, or curl/HTTP response output) showing the
  bug/absence before your change and the fix/feature after it.
- If there's a measurable surface (latency, output values, error counts):
  record actual before/after numbers, not estimates.
- Always run factory/validate.sh yourself first and fix any failures --
  the wrapper script will re-run it independently and treat a failure as
  a hard stop regardless of what you report.
- If you cannot produce real evidence for a claim, say so explicitly in the
  PR body rather than asserting it worked.

If you accept the issue and finish successfully: do not open the PR
yourself -- the wrapper script does that. Instead write your final PR
title, description, and evidence to $pr_draft in this exact format:

  TITLE: <one line>
  ---
  <PR body, including "Closes #$ISSUE_NUMBER", a summary of what changed,
  the validation results, and the before/after evidence you gathered>

If you must escalate per RULES.md (ambiguous, blocked, out of scope, or you
could not produce real evidence the fix works): do NOT make code changes,
or revert any you made. Instead write your explanation to $escalation and
stop.

Do not touch .github/workflows/, secrets, or any .env* file under any
circumstances, per MISSION.md.
EOF

rm -f "$pr_draft" "$escalation"

claude -p "$(cat "$prompt_file")" \
  --allowedTools "Read,Write,Edit,Bash,Grep,Glob" \
  --permission-mode acceptEdits

rm -f "$prompt_file"

if [ -f "$escalation" ]; then
  echo "Factory escalated on issue #$ISSUE_NUMBER" >&2
  gh issue edit "$ISSUE_NUMBER" --add-label "$LABEL_NEEDS_HUMAN" --remove-label "$LABEL_READY"
  gh issue comment "$ISSUE_NUMBER" --body-file "$escalation"
  exit 0
fi

if [ ! -f "$pr_draft" ]; then
  echo "No PR draft and no escalation produced -- treating as failure." >&2
  gh issue comment "$ISSUE_NUMBER" --body "Factory run on issue #$ISSUE_NUMBER produced no output. Needs human review."
  gh issue edit "$ISSUE_NUMBER" --add-label "$LABEL_NEEDS_HUMAN" --remove-label "$LABEL_READY"
  exit 1
fi

# Hard validation gate -- never trust the agent's self-report.
if ! bash "$FACTORY_DIR/validate.sh"; then
  echo "Validation failed after factory run on issue #$ISSUE_NUMBER." >&2
  gh issue comment "$ISSUE_NUMBER" --body "Factory attempted issue #$ISSUE_NUMBER but validation failed. Needs human review."
  gh issue edit "$ISSUE_NUMBER" --add-label "$LABEL_NEEDS_HUMAN" --remove-label "$LABEL_READY"
  exit 1
fi

pr_title="$(sed -n '1s/^TITLE: //p' "$pr_draft")"
pr_body="$(sed '1,2d' "$pr_draft")"

if git diff --quiet origin/main -- . ":(exclude)factory/.pr_draft.md" ":(exclude)factory/.escalation.md"; then
  echo "No code changes produced; not opening a PR." >&2
  gh issue edit "$ISSUE_NUMBER" --add-label "$LABEL_NEEDS_HUMAN" --remove-label "$LABEL_READY"
  exit 1
fi

git add -A -- . ":(exclude)factory/.pr_draft.md" ":(exclude)factory/.escalation.md"
git commit -m "$pr_title

$pr_body"
git push -u origin "$branch"

pr_url="$(gh pr create --title "$pr_title" --body "$pr_body" --base main --head "$branch")"
gh issue edit "$ISSUE_NUMBER" --remove-label "$LABEL_READY"

# Optional external review loop (e.g. CodeRabbit, Greptile). If configured,
# re-invoke the agent to address feedback and re-push until it clears, or a
# max round count is hit. See factory/review_loop.sh -- no-op if unset.
if [ -x "$FACTORY_DIR/review_loop.sh" ]; then
  "$FACTORY_DIR/review_loop.sh" "$ISSUE_NUMBER" "$pr_url" "$worktree_dir" "$branch" || \
    echo "Review loop did not complete cleanly; PR left for human review." >&2
fi

rm -f "$pr_draft" "$escalation"
echo "Opened PR for issue #$ISSUE_NUMBER: $pr_url"
