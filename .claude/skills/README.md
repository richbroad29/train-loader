# Vendored skills

Third-party skills installed into this project. Not authored here.

## Matt Pocock's skills

- **Source:** <https://github.com/mattpocock/skills>
- **Commit:** `959a8e9f1edc3adbe2f7e3054bb6fbefa6696260`
- **Licence:** MIT, Copyright (c) 2026 Matt Pocock
- **Installed:** 2026-09-16

`wayfinder` is the one that was wanted; the rest are its dependencies. Wayfinder calls
the Skill tool for `grilling`, `domain-modeling`, `prototype` and `research`, so it does not
work without them. `setup-matt-pocock-skills` supplies the issue-tracker configuration that
wayfinder reads before it can place a map.

| Skill | Why it is here | Upstream path |
|---|---|---|
| `wayfinder` | Requested | `skills/engineering/wayfinder` |
| `grilling` | wayfinder dependency | `skills/productivity/grilling` |
| `domain-modeling` | wayfinder dependency | `skills/engineering/domain-modeling` |
| `prototype` | wayfinder dependency (prototype tickets) | `skills/engineering/prototype` |
| `research` | wayfinder dependency (research tickets) | `skills/engineering/research` |
| `setup-matt-pocock-skills` | one-off repo configuration | `skills/engineering/setup-matt-pocock-skills` |

Upstream also ships ~30 other skills (code-review, tdd, triage, teach, handoff and so on).
They were left out deliberately — add them if you want them, don't inherit them by accident.

### Known environment caveat

The upstream GitHub tracker doc drives everything through the `gh` CLI. Claude Code on the
web has no `gh`; it uses GitHub MCP tools instead. The operations map one-to-one, but if you
configure the GitHub tracker, expect the literal `gh` commands in
`setup-matt-pocock-skills/issue-tracker-github.md` to be translated rather than run. The
local-markdown tracker has no such caveat.

### Updating

```sh
git clone --depth 1 https://github.com/mattpocock/skills.git /tmp/mp-skills
# then re-copy the six directories above, dropping each skill's agents/ dir (OpenAI configs)
```

The `agents/openai.yaml` files were stripped on install; they target another vendor.
