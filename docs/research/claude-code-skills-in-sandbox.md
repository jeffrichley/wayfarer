---
type: reference
---
# Research: can Claude Code run the skills line inside Waystation's sandbox?

Ticket: [#2](https://github.com/jeffrichley/wayfarer/issues/2) — "Can Claude Code run the skills line inside Waystation's sandbox?"
Map: [#1](https://github.com/jeffrichley/wayfarer/issues/1) — Wayfarer's first running slice
Date: 2026-09-20
Claude Code version under test: **2.1.278**

**Question.** Can Claude Code actually run the mattpocock/skills line inside Waystation's sandbox, the way `/tdd` would need to?

**Sources.** Official docs at code.claude.com (`headless.md`, `plugins-reference.md`); `claude --help` and `claude plugin … --help` on 2.1.278; the waystation source (`agents/claude_code.py`, `agents/protocol.py`, `sandbox/`, `docs/adr/0018`, `0019`); the installed plugin cache at `~/.claude/plugins/`; and **live experiments** run on this machine in the exact argv shape `ClaudeCode.command()` builds. Every experiment below was actually executed; its result is quoted, not predicted.

---

## Bottom line

**Yes, with caveats.** A `/tdd` run inside a Waystation sandbox works as designed — verified end to end, not inferred. The four caveats are: the plugin must be **baked into the image**; a missing plugin **fails silently**, not loudly; `/tdd`'s seam-confirmation step **cannot be honoured unattended**; and turn/budget limits must account for the **`StructuredOutput` tool call and its retries**. Details in [Caveats](#caveats-in-priority-order).

---

## 1. Invoking a skill in `claude -p` print mode

### It is documented, and it works on stdin

`headless.md` states it outright, under "Create a commit" → "Command support differs in `-p` mode":

> User-invoked [skills](https://code.claude.com/docs/en/skills) and custom commands work. Include `/skill-name` in the prompt string and Claude Code expands it before running.

— <https://code.claude.com/docs/en/headless.md>

The doc says "prompt string". Waystation puts the prompt on **stdin**, not argv (`AgentCommand.stdin = prompt`, `claude_code.py`; deliberate per ADR-0018 and the earlier sandcastle research, to dodge the ~128 KiB argv limit). **Verified that stdin works the same way:**

```
printf '/mattpocock-skills:tdd In one short sentence, state the FIRST rule of the loop
you were just given, verbatim. Do not use any tools.' \
  | claude -p --verbose --output-format stream-json --max-turns 1 --model sonnet
```

Result, in **turn 1, with no tool calls**:

> **"Red before green. Write the failing test first, then only enough code to pass it. Don't anticipate future tests or add speculative features."**

That is a verbatim quote of the last bullet in `skills/engineering/tdd/SKILL.md`. Expansion happens **before** the first model request: the skill body is inlined into the prompt, so the model has it on turn 1 without a `Skill` tool call.

**Consequence for Wayfarer's beat stream:** the expansion is *not* emitted as a stream event. There is no `user` event carrying the expanded text and no `tool_use` marking the skill load. The only in-stream evidence that a skill was invoked is the model's own behaviour. If Wayfarer wants a "the agent picked up /tdd" beat, it has to synthesise it from the prompt it sent, or from the `system/init` preflight in §2.

### Bare `/tdd` resolves — but use the namespaced form anyway

The plugin's canonical command name is **namespaced**. From the `system/init` event, `slash_commands` contains `mattpocock-skills:tdd`; there is **no bare `tdd` entry**.

Despite that, **unqualified `/tdd` did resolve** on 2.1.278. Two experiments confirm it:

- `/tdd …` returned the same verbatim "Red before green" rule.
- `/wait-what …` (a skill whose frontmatter is `disable-model-invocation: true`, so the model *cannot* auto-load it) caused the model to quote its exact opening sentence, "Wait, I don't understand where you've got to here." Only slash expansion can explain that.

This matches `claude --help` for `--bare`: *"Skills still resolve via `/skill-name`."*

⚠️ A doc-derived summary claimed unqualified names do **not** resolve to plugin skills. That claim is **contradicted by direct observation** and I could not find it stated in the docs themselves — treat it as unverified. Regardless, **the namespaced form `/mattpocock-skills:tdd` is the one the CLI itself advertises**, and it is immune to collisions with a same-named project skill. *Recommendation: Wayfarer should send the namespaced form.*

### An unknown command degrades to prose, silently

```
printf '/definitely-not-a-real-command-xyz Reply exactly: SAW_LITERAL if you received
this text literally. Do not use tools.' | claude -p …
```

→ exit **0**, empty stderr, result: `SAW_LITERAL`.

**An unrecognised slash command is not an error.** It is passed to the model as literal text and the run proceeds normally. This is the single most dangerous finding in this ticket; see §2 and [Caveats](#caveats-in-priority-order).

---

## 2. What the sandbox image must contain

### Plugin skills come from the config dir, never from the workspace

ADR-0018's consequences already state waystation's side of the contract:

> Whatever an agent can use comes from the image (user scope: `~/.claude` plugins, skills, settings, MCP servers, binaries) or the workspace's committed `.claude/` and `.mcp.json` (project scope); waystation injects no host paths per run and **never mounts the host's `~/.claude`**, which carries credentials (ADR-0013).

**Verified by experiment.** Re-running with `CLAUDE_CONFIG_DIR` pointed at an empty directory — which is precisely "an image with no plugin cache" — the `system/init` event reported:

| | host `~/.claude` | empty config dir |
| --- | --- | --- |
| `plugins` | 2 (`mattpocock-skills`, `agents-md`) | **`[]`** |
| `skills` | 54 | 17 (built-ins only) |
| `slash_commands` matching `tdd` | `["mattpocock-skills:tdd"]` | **`[]`** |

So `/tdd` does **not** travel with the repo. It must be in the image.

### Real cache layout (inspected locally)

```
~/.claude/plugins/
├── installed_plugins.json        # which plugins, which version, install path, git sha
├── known_marketplaces.json       # marketplace name → source (github repo / directory)
├── plugin-catalog-cache.json     # ~500 KB catalog cache
├── marketplaces/<marketplace>/   # the cloned marketplace repo (6.5 MB here)
├── cache/<marketplace>/<plugin>/<version>/   # the plugin itself (24 MB here)
└── synced/                       # plugins synced from a claude.ai account
```

Concretely, `/tdd` lives at:

```
~/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3/skills/engineering/tdd/
├── SKILL.md      # 3.5 KB, the whole skill
├── tests.md      # referenced by SKILL.md
├── mocking.md    # referenced by SKILL.md
└── agents/openai.yaml
```

`installed_plugins.json` records `"mattpocock-skills@claude-plugins-official"` with `installPath`, `version: "1.2.3"` and `gitCommitSha`. The version is **pinned in the path**, so an image can pin a known-good skills version — which matters, because the skill body is the agent's instructions and a silent upstream change would silently change behaviour. Docs confirm the versioned-directory scheme and a ~14-day orphan grace period (<https://code.claude.com/docs/en/plugins-reference.md>).

`enabledPlugins` in a `settings.json` (user `~/.claude/settings.json`, project `.claude/settings.json`, or local) records which plugins are on:

```json
{ "enabledPlugins": { "mattpocock-skills@claude-plugins-official": true } }
```

### Three ways to get the plugin into the image

| Option | Mechanism | Network at run time | Version pinning | Notes |
| --- | --- | --- | --- | --- |
| **A. Bake at build time** (recommended) | `RUN claude plugin marketplace add anthropics/claude-plugins-official && claude plugin install mattpocock-skills@claude-plugins-official -s user -y` in the Dockerfile, as the image's non-root user | **None** | Yes — the cache path carries the version; verify it after install | Matches ADR-0011 ("waystation never builds or pulls"): the image is yours to build. The whole cache is ~30 MB. |
| **B. `--plugin-dir` / `--plugin-url` per run | Append to `ClaudeCode.args`; `--plugin-dir` takes a directory **or a `.zip`** | `--plugin-dir` no; `--plugin-url` yes | Whatever you ship | Needs the plugin on a path inside the sandbox anyway, so it mostly reduces to A. Useful to override a baked version for one run. |
| **C. Install at run time | `CLAUDE_CODE_SYNC_PLUGIN_INSTALL` makes marketplace plugins install before the first turn, emitting `system/plugin_install` events | **Yes** | Weak | Rejected for Wayfarer: adds a network dependency and a failure mode to every run, and the sandbox may have no egress. |

`claude plugin install --help` (2.1.278) confirms the non-interactive path: `-s, --scope <user|project|local>` and `-y, --yes` ("Accept the displayed marketplace-declared command"), plus `--json` for a machine-readable result. `claude plugin marketplace add <source>` takes "a URL, path, or GitHub repo".

Note the **installer needs network at build time** and, per <https://code.claude.com/docs/en/discover-plugins.md>, refreshes the marketplace catalog before lookup. That is fine in a `docker build`; it is exactly what you want to avoid at run time.

Everything the earlier waystation research established about the image still applies (`docs/research/claude-headless-docker.md` next door): non-root user (`bypassPermissions` is refused as root), `HOME` set and writable, `~/.local/bin` on `PATH`, `DISABLE_AUTOUPDATER=1` and a pinned CLI version. Waystation's own `tests/sandbox/Dockerfile` is debian-slim + git + a non-root `agent` user — it has **no Claude Code and no plugins**; it is the docker test tier's image, not a template for an agent image.

### The preflight the docs hand you for free

`headless.md` has a section literally titled **"Fail CI when a plugin or MCP server doesn't load"**:

> `plugins` — plugins that loaded successfully, each with `name` and `path`
> `plugin_errors` — plugin load-time errors, each with `plugin`, `type`, and `message`. Includes unsatisfied dependency versions and `--plugin-dir` load failures such as a missing path or invalid archive. Affected plugins are demoted and absent from `plugins`. **The key is omitted when there are no errors**

Both fields ride on the `system/init` event, which is the **first line of the stream**. Since an unknown slash command is silently literal (§1), this is the only cheap, deterministic way to know `/tdd` exists before burning a run. See [Recommendations](#recommendations).

---

## 3. `--json-schema` vs the skill's own output

### No conflict — they occupy different channels

Verified by running `/tdd` **with** a schema, in Waystation's exact flag shape:

```
claude -p --verbose --output-format stream-json \
  --json-schema '<Outcome schema>' --permission-mode bypassPermissions \
  --max-turns 80 --model sonnet
```

The mechanism: the schema is exposed to the model as a **tool named `StructuredOutput`**. The skill's narrative flows normally through `assistant` text blocks; the Outcome is a *separate tool call* at the end. Nothing is truncated or replaced mid-flight.

| Channel | Carries | Waystation mapping |
| --- | --- | --- |
| `assistant` → `text` blocks | the skill's prose — "Red for the right reason", "Green. Cycle 2 is a Purse…" | `AgentText` → beats |
| `assistant` → `tool_use` blocks | `Bash`, `Edit`, … **and `StructuredOutput`** | `AgentToolUse` → beats |
| `result.structured_output` | the validated Outcome | `OutcomeReported` → core validates with pydantic |
| `result.result` | in schema runs, the same JSON as a string | unused |

This confirms ADR-0019's verification note (made on 2.1.273) still holds on 2.1.278.

Two consequences Wayfarer should know:

1. **`StructuredOutput` shows up as a tool-use beat.** It is plumbing, not work. Wayfarer's live-build screen probably wants to filter it (and the `TodoWrite`-class tools) out of the beat stream, or render it as "reporting outcome" rather than as a tool call.
2. **The CLI retries in-agent, and retries cost turns.** In the real run the model's *first* `StructuredOutput` call failed to parse: the stream carried
   `<tool_use_error>InputValidationError: StructuredOutput was called with input that could not be parsed as JSON.`
   followed by a second, successful call (`Structured output provided successfully`). Two `StructuredOutput` calls for one Outcome. This is the "the CLI itself re-prompts until the output matches" behaviour `claude_code.py`'s docstring describes — and it means **budget at least 2–3 turns of headroom purely for the Outcome**. Exhausting retries surfaces as `error_max_structured_output_retries` (ADR-0019), a non-zero exit, hence `AgentExited`.

Schema hygiene, from `headless.md`: an invalid schema is rejected outright (`Error: --json-schema is not a valid JSON Schema`); the `format` keyword is accepted but treated as an annotation and **not enforced** — so `"format": "uri"` on a PR URL buys nothing.

### What `/tdd` leaves behind that an Outcome must carry

The real run (below) produced, in the workspace:

```
 M pyproject.toml            # pytest config so the src layout imports
?? src/moneybag/money.py
?? src/moneybag/purse.py
?? tests/test_money.py
?? tests/test_purse.py
?? src/moneybag/__pycache__/ # build junk, uncommitted
```

**Nothing was committed.** `git log` still showed only the seed commit. The skill is explicit that refactoring and review are someone else's stage, and it does no git work. That fits waystation cleanly: integration is a separate stage (ADR-0020), so the **diff lives in the workspace** and the Outcome carries only the narrative. What the Outcome usefully carried:

- `summary` — three red→green cycles, what Money and Purse are, and what was deliberately left undone
- `tests_added` — three node ids, e.g. `tests/test_purse.py::test_purse_refuses_to_total_a_mix_of_currencies`
- `files_changed` — six paths
- `all_green: true`
- `blocked_on: null`

That maps onto the map's "patch series" deliverable well: **the Outcome names the tests and files; the patch series comes from the workspace, not from the Outcome.** Two things to design for:

- **`__pycache__` and friends.** An agent-run workspace accumulates build junk. Whatever turns the workspace into a patch series needs a `.gitignore` in the image or the repo, or Wayfarer will show noise as changes.
- **A `blocked_on`-shaped field earns its place.** See the next caveat for why.

---

## 4. Realistic turn and budget cost

### Measured, not guessed

One complete `/tdd` run, sonnet, `--permission-mode bypassPermissions`, `--max-turns 80`, on a **deliberately small** task (implement `Money` and `Purse` test-first in an empty Python repo with a `CONTEXT.md`):

| Metric | Value |
| --- | --- |
| `subtype` | `success`, `is_error: false` |
| **`num_turns`** | **10** |
| **`total_cost_usd`** | **$0.2047** |
| `duration_ms` | 49,380 (~49 s) |
| tool calls | 7 × `Bash`, 2 × `StructuredOutput` |
| output tokens | 5,130 (1,275 thinking) |
| cache read tokens | **199,510** |
| cache creation tokens | 28,355 |
| work produced | 3 red→green cycles, 3 passing tests, 2 modules |

Reference points from the same session: a **1-turn no-op** run costs ~$0.035–0.041 (the Claude Code system prompt plus 54 skill descriptions is ~10 k tokens of cached preamble on every single run — that is the floor). A 2-turn schema run cost $0.088.

### Extrapolation *(inference — labelled)*

Turns scale with red→green cycles, roughly **2–3 turns per cycle** (one to write the failing test and run it, one to implement and re-run, plus reconnaissance up front and 1–3 for the Outcome). The toy task was 3 cycles → 10 turns.

| Ticket size *(inferred)* | Cycles | Turns | Cost, sonnet |
| --- | --- | --- | --- |
| Toy (measured) | 3 | 10 | $0.20 |
| Small real ticket | 5–8 | 20–35 | $0.75–$2 |
| Medium ticket, existing suite | 10–15 | 40–70 | $2–$6 |
| Large / flailing on a failing suite | — | 80+ | $6–$20+ |

Cost grows **faster than turns**: 199 k cache-read tokens on a 10-turn toy run shows the whole conversation is re-read every turn, so context grows with each cycle. A run on a real repo starts with a much larger reconnaissance context (`CONTEXT.md`, ADRs, an existing test suite) and a slower test command — 49 s for a 0.00 s pytest suite is nearly all model latency, but a real suite adds wall-clock per cycle, of which there are two runs per cycle.

### What happens at the limit — verified

```
claude -p --json-schema … --max-turns 1   # on a task that needs a tool
```

→ **exit 1**, and the `result` event carried:

```
subtype: error_max_turns
is_error: true
terminal_reason: max_turns
errors: ["Reached maximum number of turns (1)"]
stop_reason: tool_use
num_turns: 2
```

and **no `structured_output`**. This is exactly the path `claude_code.py::_result_events` guards: `succeeded` is false, so no `OutcomeReported`; the non-zero exit makes it `AgentExited` (ADR-0016/0019). Waystation already handles it correctly — but note the Outcome is *lost*, not partial. A run cut off at `--max-turns` yields **no narrative at all** beyond the stdout tail, however much work it did in the workspace.

There is no wall-clock flag; time limits stay the orchestrator's job (waystation's silence/wall timers, ADR-0017).

Docs do not spell out `--max-turns` breach semantics; the table above is **measured on 2.1.278**, not quoted.

---

## Caveats, in priority order

**1. A missing plugin fails silently and expensively.** `/tdd` with no plugin installed is not an error — it is prose. The run proceeds, the model does *something* reasonable-looking, `--json-schema` dutifully produces a **valid Outcome**, and the run reports **success**. Wayfarer would show a green run that never ran TDD. This is the caveat that most changes the shape of the slice, because it means *the Outcome cannot be trusted as evidence the skill ran.*

**2. `/tdd` asks for a human and cannot get one.** `SKILL.md` says:

> **Test only at pre-agreed seams.** Before writing any test, write down the seams under test and confirm them with the user. **No test is written at an unconfirmed seam.** […] Ask: "What's the public interface, and which seams should we test?"

An unattended print-mode run has nobody to ask, and ADR-0018/map note 2 confirm there is no channel into a running agent. **The good news, verified:** the run did **not** hang or call `AskUserQuestion` (zero occurrences in the stream). It proceeded and *self-reported the deviation* in the Outcome:

> "Seams were not confirmed with the user because the session is non-interactive; I took the prompt and CONTEXT.md as defining them: Money(minor_units, currency) …"

So it degrades gracefully — but it degrades. The skill's central quality guarantee is unenforceable AFK, and the agent silently substitutes its own judgement. Two mitigations, neither requiring an upstream change to mattpocock/skills (map: "No upstream changes"): **state the seams in the prompt** Wayfarer sends, so there is nothing to confirm; and **give the Outcome a `blocked_on`/`assumptions` field** so the deviation is visible on screen instead of buried in prose. The real run populated exactly such a field correctly (`blocked_on: null`, assumptions in `summary`).

Belt and braces: `--permission-prompts none` (2.1.259+) removes `AskUserQuestion` from the toolset entirely, so a skill that insists on asking is denied and told not to retry, rather than stalling. Worth adding to `ClaudeCode.args` for AFK runs.

**3. Turn and budget caps must leave Outcome headroom.** `StructuredOutput` is a real tool call that can fail validation and retry (observed: 2 calls for 1 Outcome). A cap hit before it lands loses the Outcome entirely — `error_max_turns`, no `structured_output`, `AgentExited`. Set `max_turns` with margin and prefer `max_budget_usd` as the real guard, since cost — not turn count — is what actually runs away.

**4. `--bare` is a future landmine.** `headless.md`: *"`--bare` is the recommended mode for scripted and SDK calls, and **will become the default for `-p` in a future release**."* Bare mode skips "auto-discovery of hooks, skills, custom commands, subagents, plugins, MCP servers, auto memory, and CLAUDE.md" — i.e. **it would turn `/tdd` off**. Waystation does not pass `--bare` today, so this is fine now; when the default flips, `ClaudeCode` will need an explicit opt-out, and the `system/init` preflight in Recommendation 1 is what would catch it. *Worth filing on `jeffrichley/waystation` (map: "Waystation changes may be named, not built").*

**5. Minor:** the skills preamble costs ~$0.04 and ~10 k cached tokens on every run before any work happens; `/tdd` leaves `__pycache__`-class junk in the workspace that a patch series must ignore; and the skill expansion produces **no stream event**, so "the agent picked up /tdd" is not observable from the beat stream alone.

---

## Recommendations

1. **Preflight on `system/init`, not on faith.** It is the first line of the stream, free, and deterministic. Assert `mattpocock-skills` ∈ `plugins`, `mattpocock-skills:tdd` ∈ `slash_commands`, and `plugin_errors` absent. Fail the run there rather than after $5 of prose. The docs endorse exactly this ("Fail CI when a plugin or MCP server doesn't load"). *This is a Waystation-shaped capability — `ClaudeCode.parse` currently discards `system` events entirely — so it is a candidate issue on `jeffrichley/waystation`, not Wayfarer work.*
2. **Send the namespaced form**, `/mattpocock-skills:tdd <ticket>`, on stdin. It is what the CLI advertises and it cannot collide.
3. **Bake the plugin into the image at a pinned version** (option A), and verify the pin in the build, not at run time.
4. **Put the seams in the prompt** and give the Outcome schema an `assumptions` / `blocked_on` field so unattended deviation is visible.
5. **Set `max_budget_usd` as the primary guard** and `max_turns` generously; add `--permission-prompts none` to `args`.

---

## Verified-vs-inferred ledger

**Verified (observed on 2.1.278, this machine):** slash expansion works on stdin in `-p`; both namespaced and bare forms resolve; unknown commands become literal prose with exit 0; an empty config dir removes the plugin, its skills and its slash commands; `--json-schema` is implemented as a `StructuredOutput` tool and coexists with skill prose; it retries on malformed input; `--max-turns` breach gives `error_max_turns` + exit 1 + no `structured_output`; a 3-cycle `/tdd` run = 10 turns / $0.20 / 49 s; `/tdd` commits nothing and does not hang on the seam question but self-reports skipping it.

**Quoted from docs:** the `/skill-name` expansion sentence; `plugins` / `plugin_errors` on `system/init`; `--bare` semantics and its future-default note; schema validation and `format`-as-annotation; plugin cache layout and `enabledPlugins`.

**Inference (labelled as such):** the turns-and-cost extrapolation table for larger tickets. Everything else above is measured or quoted.
