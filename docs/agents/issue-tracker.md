# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues on `richbroad29/train-loader`.

## Two ways to reach GitHub

The operations below are written for the `gh` CLI, which is how Matt's skills assume you
reach GitHub. **Claude Code on the web has no `gh`** — it reaches GitHub through MCP tools
instead. Check which you have and use it; the semantics are identical.

| Operation | `gh` CLI | MCP tool |
|---|---|---|
| Create an issue | `gh issue create` | `issue_write` (method `create`) |
| Read an issue | `gh issue view <n> --comments` | `issue_read` (method `get` / `get_comments`) |
| List issues | `gh issue list` | `list_issues` |
| Comment | `gh issue comment <n>` | `add_issue_comment` |
| Add / remove labels | `gh issue edit <n> --add-label` | `issue_write` (method `update`, `labels`) |
| Assign | `gh issue edit <n> --add-assignee @me` | `issue_write` (method `update`, `assignees`) |
| Close | `gh issue close <n>` | `issue_write` (method `update`, `state: closed`) |
| Link a sub-issue | `gh api` sub-issues endpoint | `sub_issue_write` |
| Issue dependencies (`blocked_by`) | `gh api .../dependencies/blocked_by` | **not exposed** — see below |

## Conventions (`gh`)

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v`; `gh` does this automatically when run inside a clone.
MCP tools take `owner` and `repo` explicitly: `richbroad29` / `train-loader`.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either: resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`, or `issue_read`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Destination / Notes /
  Decisions-so-far / Not-yet-specified / Out-of-scope body.
  `gh issue create --label wayfinder:map`, or `issue_write` with that label.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the
  sub-issues endpoint, or the `sub_issue_write` MCP tool). Where sub-issues aren't enabled,
  add the child to a task list in the map body and put `Part of #<map>` at the top of the
  child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once
  claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies** are the canonical, UI-visible
  representation. With `gh`: `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`,
  where `<blocker-db-id>` is the blocker's numeric **database id**
  (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or `node_id`).
  GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only, the live gate).

  **No MCP tool exposes the dependencies endpoint.** In a web session, fall back to a
  `Blocked by: #<n>, #<n>` line at the top of the child body, and say so when you do — the
  frontier is then readable only from the text, not from GitHub's UI. A ticket is unblocked
  when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, or
  `list_issues`, scoped to the map's sub-issues / task list), drop any with an open blocker
  (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line)
  or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me`, or `issue_write` with `assignees`.
  The session's first write.
- **Resolve**: comment the answer, close the issue, then append a context pointer
  (gist + link) to the map's Decisions-so-far.
