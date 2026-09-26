---
name: test-gate
description: 'Run the read-only test-gate agent to approve or reject test cases and confirm nothing broke. Use after finishing a ticket by hand, before committing or pushing, after merging a teammate''s branch, and as the final pre-demo check. implement-ticket already runs it automatically. Input - an issue number/URL or ticket text to gate one ticket, "full" for a whole-project demo-readiness audit, or blank to gate the current uncommitted changes.'
argument-hint: '<issue number | ticket text | full | blank>'
---

Gate target (may be blank):

$ARGUMENTS

## Step 1 - Pick the mode

- **Issue number / URL** - read it with `gh issue view <n>`. Mode `ticket`.
- **Pasted ticket text** - mode `ticket`.
- **`full`** - mode `full`: whole-project demo-readiness audit, no single ticket.
- **Blank** - mode `diff`: gate whatever is in `git status` / `git diff HEAD` (plus
  `git diff main...HEAD` if on a branch). If there are no changes either, switch to `full`
  and say so.

## Step 2 - Gather what the agent needs

- `git status`, `git diff HEAD --stat`, and the list of changed test files.
- For `ticket` mode, the ticket text verbatim.
- If this conversation already recorded a baseline (e.g. from `implement-ticket` Step 0),
  include it. Otherwise say "no baseline" - the agent then treats every failing check as
  blocking, because it cannot prove the failure was already there. Do not stash or reset the
  user's changes to produce a baseline.

## Step 3 - Run the agent

Spawn `subagent_type: test-gate` in the foreground (`run_in_background: false`) with a fully
self-contained prompt: the mode, the ticket (if any), the diff summary, the baseline (or
"no baseline"), and the instruction to follow its own steps and output format.

## Step 4 - Report

Show the agent's verdict block verbatim, then one line on what that means:
- **APPROVE** - safe to commit/push if the user asks. Do not commit or push on your own.
- **BLOCK** - list the blocking findings as a short to-do. Do not fix anything automatically;
  ask the user whether you should fix them, they will, or they are overriding the gate. An
  override must be in the user's own words and should be mentioned if you later commit.
