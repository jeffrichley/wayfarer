# wayfarer-base: what every session needs that only Wayfarer knows (ADR-0005).
# A repo's own layer, `.wayfarer/Dockerfile`, starts `FROM wayfarer-base` and adds
# its toolchain. The pins arrive as build args from `wayfarer.image`, and are part
# of the tag's hash, so moving one is a deliberate edit that makes a new tag.
# Pinned by digest, so the tag names the same starting point every time it is built.
FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251

ARG CLAUDE_CODE_VERSION
ARG SKILLS_COMMIT

# python3 is the system Python `wf-test` runs on, whatever the repo's layer adds.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl gh git python3 \
    && rm -rf /var/lib/apt/lists/*

# Claude Code refuses bypassPermissions as root, so sessions run as `agent`, who
# owns the workspace.
RUN useradd --create-home --uid 1000 --shell /bin/bash agent \
    && mkdir /workspace \
    && chown agent:agent /workspace

COPY --chmod=755 wf-test /usr/local/bin/wf-test
# How a session asks by ending (#42): `wf-ask` defers the question and later hands
# back its answer; `wf-ask-tool` is the permission prompt tool a session is named,
# without which print mode offers no way to ask at all.
COPY --chmod=755 wf-ask wf-ask-tool /usr/local/bin/

USER agent
ENV HOME=/home/agent \
    PATH=/home/agent/.local/bin:$PATH \
    DISABLE_AUTOUPDATER=1

RUN curl -fsSL https://claude.ai/install.sh | bash -s "$CLAUDE_CODE_VERSION"

# The plugin is installed here, at its pin, so a session needs no network for it.
# A missing plugin fails silently, which is why each tag is probed for it.
RUN git clone --quiet https://github.com/mattpocock/skills.git "$HOME/.wayfarer/skills" \
    && git -C "$HOME/.wayfarer/skills" checkout --quiet "$SKILLS_COMMIT" \
    && claude plugin marketplace add "$HOME/.wayfarer/skills" \
    && claude plugin install mattpocock-skills@mattpocock --scope user

# `wf-ask` runs before every question, beside whatever the plugin's install wrote.
RUN python3 -c 'import json, pathlib; \
p = pathlib.Path.home() / ".claude/settings.json"; \
s = json.loads(p.read_text()) if p.exists() else {}; \
s.setdefault("hooks", {}).setdefault("PreToolUse", []).append( \
    {"matcher": "AskUserQuestion", "hooks": [{"type": "command", "command": "/usr/local/bin/wf-ask"}]}); \
p.write_text(json.dumps(s, indent=2))'

# The standing rules every session follows, under the repo's own CLAUDE.md.
COPY --chown=agent:agent CLAUDE.md /home/agent/.claude/CLAUDE.md

WORKDIR /workspace
