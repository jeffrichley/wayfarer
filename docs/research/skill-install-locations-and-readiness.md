# Where installed skills live, and what a readiness check can detect

**Ticket:** [#3](https://github.com/jeffrichley/wayfarer/issues/3) · **Map:** [#1](https://github.com/jeffrichley/wayfarer/issues/1) · Researched 2026-09-20 against Claude Code **2.1.278** on macOS 25.6.0.

Sources are labelled: **[docs]** = code.claude.com/docs, **[cli]** = `--help` output of the installed binary, **[obs]** = direct filesystem or command observation on this machine, **[inf]** = inference, marked as such.

---

## Bottom line first

**A skill's availability is not a property of a repo.** Three of the six places a skill can live are per-user or per-machine and leave no trace inside the checkout. Wayfarer's readiness panel and route band can honestly say *"`/tdd` is available to a Claude Code session started in this directory, on this machine, as this user"* — and nothing stronger. It cannot say the repo is ready for a teammate, for CI, or for a sandbox.

There is no supported command that enumerates every loaded skill. `claude plugin list --json` is a stable, machine-readable contract but it **under-reports**: it missed a plugin that a live session in the same directory actually loaded ([obs](#observed-gap-plugin-list-under-reports)). The honest answer is a **union of six sources**, described below, all of them cheap.

---

## 1. Every location a skill can be installed from

### 1.1 The documented table

**[docs]** `https://code.claude.com/docs/en/skills.md` lists exactly seven load locations:

| Location | Path | Loads in |
|---|---|---|
| Enterprise | `.claude/skills/<skill-name>/SKILL.md` inside the managed settings directory | All users on machines where the org deploys it |
| Personal | `~/.claude/skills/<skill-name>/SKILL.md` | All your projects on this machine, but not Cowork or cloud sessions |
| Project | `.claude/skills/<skill-name>/SKILL.md` | Sessions in this repository. Commit it so your team gets it too |
| Nested | `<subdir>/.claude/skills/<skill-name>/SKILL.md` | Sessions started in or below `<subdir>` |
| Additional directory | `.claude/skills/<skill-name>/SKILL.md` in a directory passed with `--add-dir` | That session only |
| Plugin | `<plugin>/skills/<skill-name>/SKILL.md` | Wherever the plugin is enabled, **as `/plugin-name:skill-name`** |
| claude.ai account | Skills enabled for your claude.ai account | Cowork, cloud, and terminal sessions signed in with that account |

Plus **bundled skills** shipped inside the CLI itself (`/code-review`, `/simplify`, `/init`, `/security-review`, `dataviz`, …) — **[obs]** these appear in a session with no plugin and no `.claude/skills` present.

**[docs]** The managed settings directory is system-wide, not per-user (`https://code.claude.com/docs/en/managed-settings.md`):

> `/Library/Application Support/ClaudeCode/` on macOS, `/etc/claude-code/` on Linux and WSL, and `C:\Program Files\ClaudeCode\` on Windows.

**[obs]** Neither exists on this machine.

### 1.2 What each looks like on disk here

**Plugin cache — the mattpocock case.** `~/.claude/plugins/`:

```
~/.claude/plugins/
├── installed_plugins.json        # install records, version 2
├── known_marketplaces.json       # marketplace name -> source + installLocation
├── plugin-catalog-cache.json     # ~500 KB catalogue cache
├── cache/<marketplace>/<plugin>/<version>/   # the plugin tree itself
├── marketplaces/<marketplace>/               # cloned marketplace repo
└── synced/<uuid>_<uuid>/.marketplaces.json   # claude.ai account sync
```

**[obs]** `installed_plugins.json`:

```json
{
  "version": 2,
  "plugins": {
    "mattpocock-skills@claude-plugins-official": [
      {
        "scope": "user",
        "installPath": "/Users/jeffrichley/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3",
        "version": "1.2.3",
        "installedAt": "2026-09-13T23:25:24.059Z",
        "gitCommitSha": "3cca18b368ae95cdbdebbff572ccafa662551015"
      }
    ]
  }
}
```

**[obs]** The plugin tree at that `installPath` is the upstream git repo, with `.claude-plugin/plugin.json` carrying an explicit `skills` array of 25 relative paths, and the skills themselves grouped in category folders:

```
1.2.3/
├── .claude-plugin/plugin.json      # name, version, skills: ["./skills/engineering/tdd", ...]
├── .claude-plugin/marketplace.json
└── skills/
    ├── engineering/{tdd,to-spec,to-tickets,wayfinder,code-review,research,...}/SKILL.md
    ├── productivity/{grilling,handoff,teach,...}/SKILL.md
    ├── in-progress/…  misc/…  deprecated/…     # NOT in plugin.json's skills[] — not loaded
```

The ticket's guess ("a plugin cache under `~/.claude/plugins/cache/`, versioned, with skills grouped in category folders") is **confirmed exactly**.

**[docs]** `plugins-reference.md`: the `skills` field is optional and **adds to** the default — "The default `skills/` directory is always scanned, and directories listed in `skills` are loaded alongside it." So `skills/in-progress/*` and `skills/misc/*` *are* under `skills/`… **[inf]** but they are nested two levels deep and Claude Code's default scan is `skills/<name>/SKILL.md`, one level. **[obs]** corroborates: `claude plugin details mattpocock-skills` reports exactly **Skills (25)**, matching `plugin.json` and excluding `in-progress`/`misc`/`deprecated`. Do not infer the skill set by globbing `skills/**/SKILL.md` — that over-counts 12 skills here.

**Personal skills.** **[obs]** `~/.claude/skills/` contains only `synced/` — no hand-written personal skills on this machine. The account-sync tree:

```
~/.claude/skills/synced/<uuid>_<uuid>/
├── manifest.json        # {"lastUpdated": …, "skills": [{skillId, name, description}, …]}
├── docs/SKILL.md  pdf/SKILL.md  xlsx/SKILL.md  pptx/SKILL.md  …
```

**[obs]** These load as `anthropic-skills:<name>`. They are bound to the **claude.ai account**, not the machine and not the repo.

**Project skills.** **[obs]** A real example next door — `~/workspaces/ai/bookwright/.claude/skills/` holds 29 directories, each a vendored copy of a mattpocock skill (`wayfinder/SKILL.md` there is byte-similar to the plugin's, with slightly older wording). They are **git-tracked** (`git ls-files .claude/skills` lists them). This is the only genuinely per-repo skill install.

**Project-declared plugins.** **[obs]** Two real examples:

```jsonc
// ~/workspaces/ai/skill-library/.claude/settings.json
{ "enabledPlugins": { "hpc@jazz-hpc": true, "plugin-dev@claude-plugins-official": true } }

// ~/workspaces/dreams/chrona/.claude/settings.json
{
  "extraKnownMarketplaces": { "chrona": { "source": { "source": "directory", "path": "." } } },
  "enabledPlugins": { "operator@chrona": true }
}
```

**[docs]** `settings-reference.md` documents both keys; `discover-plugins.md` documents the team workflow ("Team admins can set up automatic marketplace installation for projects by adding marketplace configuration to `.claude/settings.json`"). These are **supported, committed contracts**, not internals.

**[docs]** caveat, `discover-plugins.md`: "As of Claude Code v2.1.195, adding the marketplace doesn't install plugins that come from an external source… A plugin that only the project's `.claude/settings.json` enables, and that comes from an external source such as a GitHub repository or npm package, doesn't load until the team member installs it." So a committed `enabledPlugins` entry pointing at a GitHub/npm marketplace is a **declaration of intent, not a guarantee of presence**.

---

## 2. Per-repo vs per-user — the conclusion that matters

| Location | Scope | Visible from inside the checkout? |
|---|---|---|
| Enterprise / managed | **Per-machine**, system-wide | No |
| Personal `~/.claude/skills/` | **Per-user** | No |
| Plugin installed `--scope user` | **Per-user** | No |
| claude.ai account sync | **Per-account** | No |
| Bundled in the CLI | **Per-CLI-version** | No |
| Project `.claude/skills/` | **Per-repo**, committable | **Yes** |
| Project `.claude/settings.json` `enabledPlugins` / `extraKnownMarketplaces` | **Per-repo**, committable — a *declaration*, satisfied per-user | **Yes (the declaration)** |
| `.claude/settings.local.json` (`--scope local`) | **Per-repo × per-user**, gitignored | Yes, but not shareable |

**[cli]** `claude plugin install -s, --scope <scope>` — "Installation scope: user, project, or local (**default: "user"**)".

### The explicit conclusion

**On this machine the mattpocock skills are installed per-user** — `scope: "user"`, in `~/.claude/plugins/cache/`, with **nothing at all inside the wayfarer checkout**: **[obs]** wayfarer has no `.claude/` directory whatsoever. Yet `/wayfinder`, `/tdd`, `/to-spec`, `/to-tickets` and `/code-review` all work here.

So: **"is `/tdd` available in this repo?" is not a property of the repo.** It is a property of *(this machine × this user account × this CLI version × this directory)*. The same repo cloned by a teammate would answer differently, with no change to a single tracked file.

**What this changes for the first-run screen.** `docs/screens/first-run.md` currently has the route band claim, per station, "Installed" / "Not installed", and the sample gap reads *"`/code-review` is missing. The station's title says what that means: add it from mattpocock/skills and agents review PRs before you do."* That wording is only honest if it is scoped to the person reading it. Two concrete corrections:

1. **Scope the sentence to the reader, not the repo.** "Available to you here" rather than "installed in this repo". Where the source is per-user, say so — the panel already says it "read what `/setup-matt-pocock-skills` wrote", which implies a repo-local record that does not exist for a plugin install.
2. **`/code-review` is the worst possible example of a gap.** **[obs]** Claude Code ships a *bundled* `code-review` skill, and `mattpocock-skills:code-review` is a different skill with different behaviour. A naive name check reports "installed" when the mattpocock station is absent. **[docs]** `skills.md` precedence table: "Your skill replaces the bundled command, but not its aliases." Wayfarer must match on **source + qualified name**, not on the bare word `code-review`.

### A third honesty problem: the station commands are namespaced

**[docs]** "Plugin skills are always namespaced (like `/my-first-plugin:hello`) to prevent conflicts." **[obs]** confirmed — a live session lists `mattpocock-skills:tdd`, not `tdd`. So with the plugin install, the stations are `/mattpocock-skills:tdd` etc.; only the bookwright-style vendored `.claude/skills/tdd/` gives a bare `/tdd`. **The route band's station labels (`/tdd`, `/to-spec`, …) are not what the user types**, and what they type depends on which install route they took. Worth a ticket.

---

## 3. Can installed skills be enumerated reliably, without internal paths?

### The supported surface

**[cli]** `claude plugin --help` on 2.1.278:

```
details <name>   Show a plugin's component inventory and projected token cost
list [options]   List installed plugins        (--json, --available)
marketplace list                               (--json)
validate <path>                                (--json, --strict)
enable/disable/install/uninstall/update        (--json, -s/--scope)
init|new <name>  Scaffold a new plugin at ~/.claude/skills/<name>/
                 (auto-loads next session as <name>@skills-dir)
```

**[obs]** `claude plugin list --json`, run in wayfarer, **0.14 s**:

```json
[{"id":"mattpocock-skills@claude-plugins-official","version":"1.2.3","scope":"user","enabled":true,
  "installPath":"/Users/jeffrichley/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3",
  "installedAt":"2026-09-13T23:25:24.059Z","lastUpdated":"2026-09-13T23:25:24.059Z"}]
```

This is the best contract available: stable JSON, includes `scope`, `enabled`, and — critically — hands back `installPath` so Wayfarer **never has to know the cache layout**.

**[obs]** `claude plugin details mattpocock-skills`, **0.45 s**, prints the inventory in plain text:

> `Skills (25)  ask-matt, code-review, codebase-design, diagnosing-bugs, domain-modeling, grill-me, grill-with-docs, grilling, handoff, implement, improve-codebase-architecture, prototype, research, resolving-merge-conflicts, setup-matt-pocock-skills, tdd, teach, to-questionnaire, to-spec, to-tickets, triage, wait-what, wayfinder, wizard, writing-for-agents`

**[cli]** `details` has **no `--json`** (only `-h`). **[docs]** `plugins-reference.md` doesn't document `--json` on `list` either, even though **[obs]** the binary supports it — so `list --json` is *implemented but under-documented*. **[inf]** Treat `list --json` as the primary path and be ready for its shape to shift; treat scraping `details` text as a fallback, since text output is the likelier thing to change.

### Observed gap: `plugin list` under-reports

**[obs]** The decisive experiment. In `~/workspaces/dreams/chrona`, whose committed `.claude/settings.json` enables `operator@chrona` from a **directory** marketplace:

- `claude plugin list --json` → **only** `mattpocock-skills@claude-plugins-official`. No `operator`.
- `claude plugin marketplace list --json` → **both** `chrona` (directory) and `claude-plugins-official`.
- `claude plugin details operator@chrona` → resolves fine, reports `Skills (4)  curating-a-channel-vault, naming-library-properties, running-an-episode, writing-a-score`.
- A **live session** started in that directory listed `operator:curating-a-channel-vault, operator:naming-library-properties, operator:running-an-episode, operator:writing-a-score` among its skills.

So the plugin **loads** but does not appear in `plugin list`. **[inf]** `plugin list` reads install records (`installed_plugins.json`), and a directory-sourced, project-enabled plugin has no install record — it is enabled, not installed. **Consequence: `claude plugin list` alone is not a sound basis for "not installed".**

### And the model-side probe under-reports too

**[obs]** That same live session listed only **11** of the plugin's 25 skills — `wayfinder`, `to-spec`, `to-tickets`, `triage`, `implement`, `handoff` and others were absent. **[docs]** `skills.md`: "Skills with `disable-model-invocation: true` won't appear in Claude's context but remain available via `/` menu for you to invoke." **[obs]** `wayfinder/SKILL.md` does carry `disable-model-invocation: true`. So asking a session what skills it has systematically omits exactly the stations Wayfarer cares most about. **Do not enumerate by launching a session.**

**[obs]** `/skills` is interactive-only: `claude -p "/skills"` answers *"`/skills` isn't available in this environment."* There is no `claude skill`/`claude skills` top-level command.

### Recommended enumeration: a union of six cheap reads

No single call is sufficient. **[inf]** The defensible recipe, in order, none of which touches an undocumented path:

1. `claude plugin list --json` → for each entry, read `<installPath>/.claude-plugin/plugin.json` and take `skills[]` (documented manifest field); fall back to `<installPath>/skills/*/SKILL.md` when absent. Names come from each `SKILL.md`'s `name` frontmatter, namespaced `plugin:name`.
2. Read the repo's `.claude/settings.json` and `.claude/settings.local.json` → `enabledPlugins`, `extraKnownMarketplaces`. Resolve each id against `claude plugin marketplace list --json`, then `claude plugin details <id>` (or that marketplace's plugin dir) for its skill names. **This is what closes the gap in §"Observed gap".**
3. Glob `<repo>/.claude/skills/*/SKILL.md` — bare-named, committed, genuinely per-repo.
4. Glob `~/.claude/skills/*/SKILL.md` — personal, bare-named.
5. Read `~/.claude/skills/synced/*/manifest.json` — account-synced, namespaced `anthropic-skills:`. **[inf]** `manifest.json` is not a documented contract; treat as best-effort and degrade quietly.
6. Bundled skills — **[inf]** not enumerable from outside at all. Accept as a known blind spot, and never let a bare-name match against a bundled skill count as a station being present.

Steps 1, 3 and 4 are documented contracts. Step 2 rests on two documented settings keys. Only steps 5 and 6 are soft. **Nothing in this recipe hard-codes `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`.**

---

## 4. The other readiness signals — reachability and cost

All measured on this machine, warm, from the wayfarer checkout.

| Signal | How | Measured | Verdict |
|---|---|---|---|
| `docs/agents/issue-tracker.md` exists | `stat` | **[obs]** present | ~0 ms — **every page load** |
| `docs/agents/triage-labels.md` exists | `stat` | **[obs]** present | ~0 ms — **every page load** |
| `docs/agents/*` (all three: `domain.md`, `issue-tracker.md`, `triage-labels.md`) | `readdir` | **[obs]** present | ~0 ms — **every page load** |
| `CONTEXT.md` or `CONTEXT-MAP.md` | `stat` | **[obs]** `CONTEXT.md` present at repo root (just moved from `docs/`) | ~0 ms — **every page load** |
| ADR count under `docs/adr/` | `readdir`, count `*.md` | **[obs]** `docs/adr/` **does not exist** — count 0 | ~0 ms — **every page load** |
| Whole filesystem block above, together | one shell round-trip | **[obs]** **10 ms** | **every page load** |
| Labels `wayfinder:map`, `wayfinder:research\|prototype\|grilling\|task` | `gh api repos/:o/:r/labels` | **[obs]** **0.36 s**; all five present | network — **cache** |
| Label `ready-for-agent` | same call | **[obs]** **absent on this repo** | network — **cache** |
| Maps exist | `gh issue list --label wayfinder:map --json` | **[obs]** **0.55 s**; returns #1 | network — **cache** |
| `claude plugin list --json` | subprocess | **[obs]** **0.14 s** | borderline — **cache, short TTL** |
| `claude plugin details <plugin>` | subprocess, one per plugin | **[obs]** **0.45 s** each | **cache**, invalidate on plugin-file mtime |

**[obs]** GitHub REST rate limit is 5000/hour core, unused at time of measurement. Both label and issue queries are single REST calls.

**Recommendation.** Compute the **filesystem block on every page load** — it is 10 ms for everything, and it is the block most likely to change while the user is looking at the screen. **Cache the GitHub block** (labels + map presence) with a short TTL, refreshed on focus or on an explicit action, since a half-second of network on every render is the difference between the route band feeling instant and feeling like a page. **Cache the skill enumeration** keyed on the mtimes of `~/.claude/plugins/installed_plugins.json`, the repo's `.claude/settings*.json`, and the repo's `.claude/skills/` — a full enumeration costs `0.14 s + 0.45 s × plugins`, which is too much per render but trivial once per session.

**Two observations worth a ticket of their own:** this repo has **no `docs/adr/`** and **no `ready-for-agent` label**, yet `docs/design/data-and-commands.md` treats both as readiness inputs. The first-run screen needs a truthful rendering of "signal absent" that is not scored as failure — `docs/screens/first-run.md` already does this for Wayfinder labels ("Created with your first map", shown as pending rather than missing). ADRs and `ready-for-agent` want the same treatment.

---

## 5. Bottom line: what a readiness check can and cannot honestly say

| Signal | Can honestly say | Cannot say |
|---|---|---|
| **`.claude/skills/<name>/`** | "This repo ships this skill to everyone who clones it." A real, committed, per-repo fact. | Nothing — this one is fully honest. |
| **`.claude/settings.json` `enabledPlugins` / `extraKnownMarketplaces`** | "This repo asks for this plugin." | "It is present." **[docs]** an external-source plugin doesn't load until each person installs it. Render as *declared*, not *installed*. |
| **`claude plugin list --json`** | "This plugin is installed for **you, on this machine**, at this version." | "…in this repo" — the install is per-user and leaves nothing in the checkout. Nor "not installed": **[obs]** it missed a plugin that a live session loaded. |
| **`claude plugin details <id>`** | "This plugin provides these 25 skills." Authoritative for skills, one exec per plugin. | Nothing about *this* repo, and no `--json`, so it is text-scraping. |
| **Personal `~/.claude/skills/`, account sync, bundled** | "Available to you." | Anything about the repo, the team, CI, or a Waystation sandbox. |
| **Station present at all** | "A session you start here can run this station." | "This station is spelled `/tdd`." **[obs]** via the plugin it is `/mattpocock-skills:tdd`. Spelling depends on install route. |
| **`/code-review` in particular** | Only meaningful as `mattpocock-skills:code-review`. | "`/code-review` exists ⇒ the station is ready" — **[obs]** a bundled `code-review` ships with the CLI and is a different skill. Match source + qualified name. |
| **`docs/agents/*`, `CONTEXT.md`, ADR count** | "This repo has been set up." Committed, instant, fully honest per-repo facts. | Nothing. These are the only readiness signals that are *purely* properties of the repo. |
| **`wayfinder:*` labels** | "This repo's tracker has been charted at least once." | "The skills are installed." Labels are created by the first map, not by installing anything. |
| **`ready-for-agent` label** | "Triage is wired." | **[obs]** absent here — say "not yet created", not "missing". |

**The one-sentence version for the first-run screen:** readiness splits cleanly into **repo facts** (`docs/agents/*`, `CONTEXT.md`, ADRs, labels, `.claude/skills/`, `.claude/settings.json` declarations — committed, instant, honest) and **your-machine facts** (everything plugin- or user-level). The screen should draw that line visibly rather than presenting one undifferentiated checklist, because only the first half is what a teammate would see.

---

## Open, and what it would take to close

- **[inf]** Whether `claude plugin install --scope project` writes an install record that `plugin list` then reports as `scope: "project"`. **[cli]** the flag exists; **[obs]** no project-scope install existed on this machine to observe, and I did not mutate config to create one. Closing it costs one install + uninstall in a scratch repo.
- **[inf]** Whether Waystation's sandboxed runs inherit `~/.claude` at all. If they do not, per-user skills are absent inside the sandbox and "readiness" means something different again for an AFK run than for the person's own terminal. This bears directly on the map's first slice and deserves its own ticket.
- **[obs]** `claude plugin list --json` exists in 2.1.278 but **[docs]** does not document it. If Wayfarer depends on it, pin a version check and degrade to `plugin list` text.
