# wayfarer-base: what every session needs that only Wayfarer knows (ADR-0005).
# A repo's own layer, `.wayfarer/Dockerfile`, starts `FROM wayfarer-base` and adds
# its toolchain. The pins arrive as build args from `wayfarer.image`, and are part
# of the tag's hash, so moving one is a deliberate edit that makes a new tag.
FROM debian:bookworm-slim

ARG CLAUDE_CODE_VERSION
ARG SKILLS_COMMIT

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl gh git \
    && rm -rf /var/lib/apt/lists/*

# Claude Code refuses bypassPermissions as root, so sessions run as `agent`, who
# owns the workspace.
RUN useradd --create-home --uid 1000 --shell /bin/bash agent \
    && mkdir /workspace \
    && chown agent:agent /workspace

COPY --chmod=755 wf-test /usr/local/bin/wf-test

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

WORKDIR /workspace
