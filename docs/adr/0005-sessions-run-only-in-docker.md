---
type: adr
title: Sessions run only in Docker, in an image built from Wayfarer's base and the repo's layer
status: stable
---

# Sessions run only in Docker, in an image built from Wayfarer's base and the repo's layer

Every session runs in a Docker container. There is no unsandboxed mode, not even behind a flag. The container's image is two parts: **`wayfarer-base`**, whose recipe Wayfarer owns (a non-root user, git, a pinned Claude Code CLI, the mattpocock-skills plugin installed at a pinned version, and `wf-test`), and **the repo's layer**, a Dockerfile committed at `.wayfarer/Dockerfile` that starts `FROM wayfarer-base` and adds the repo's toolchain. A repo with no layer is refused. Wayfarer never falls back to the bare base.

Why: sessions run unattended with `bypassPermissions`, several at once, while nobody watches. The sandbox is the only trust boundary, and it does more work with N sessions than with one. A `/tdd` session also runs the repo's tests inside the container, so the image has to hold a toolchain only the repo knows, while the plugin pin and `wf-test` are things only Wayfarer knows. A layer splits the image along exactly that line. Without a toolchain, every red would look like the agent's fault.

## Considered options

- **Bubblewrap.** Rejected: Linux only, and Waystation has no backend for it (its ADR-0010 only names it as possible).
- **`NoSandbox` behind an explicit flag.** Rejected: it puts an unsafe mode in the product before anyone needs one. Wayfarer's own development uses recorded sessions and Waystation's fakes instead.
- **Any image the user names, checked by a probe.** Kept only as the probe. On its own it leaves the user to rediscover what the plugin pin and `wf-test` require.
- **One fat generic image, installing dependencies at the start of each session.** Rejected: every session pays the install, and anything unusual still fails.
- **Keeping the layer outside the checkout.** Rejected: the toolchain belongs to the code, so the layer is versioned with it.

## Consequences

**Wayfarer builds images, which Waystation never does** (its ADR-0011). Building happens only when a person asks. The tag is a hash of the base recipe, the CLI pin, the plugin pin and the layer, so a stale image is a missing tag and cannot drift silently. Moving a pin is a deliberate edit, never "latest".

**Each tag is probed once, right after its build.** The probe checks the CLI version, the plugin at its pin via `claude plugin list --json`, `wf-test` on `PATH`, and a non-root user who owns `/workspace`. This exists because a missing plugin fails silently: the run goes green, the Outcome is valid, and no TDD happened.

**Dependencies are the repo's choice.** The layer must carry the toolchain. It may pre-install dependencies from the lockfile as a warm cache, and sessions install whatever they need either way. Wayfarer has no setup-command concept.

**Limits come through Waystation's `run_args`.** Per-container `--memory`, `--cpus` and `--pids-limit` need no Waystation change. Networking is Docker's default. An egress allowlist is out of scope for the first slice.

Decided in [Sandbox and workspace: running many agents at once](https://github.com/jeffrichley/wayfarer/issues/10).
