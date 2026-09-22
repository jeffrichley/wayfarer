"""Build the React app into the package, so the wheel carries it (ADR-0004).

A person installing Wayfarer needs no Node toolchain: the Vite build runs here,
at package build time, into `src/wayfarer/static`. Editable installs skip it, so
`uv sync` never needs Node; develop the page against `pnpm dev` instead.

The sdist ships the built bundle rather than `web/`, so a wheel built from the
sdist needs no Node either.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class WebBuildHook(BuildHookInterface):  # type: ignore[type-arg]
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if version == "editable":
            return
        root = Path(self.root)
        web = root / "web"
        static = root / "src" / "wayfarer" / "static"
        if (web / "package.json").is_file():
            _run_pnpm(web, "install", "--frozen-lockfile")
            _run_pnpm(web, "build")
        if not (static / "index.html").is_file():
            raise RuntimeError(
                f"{static} holds no built front end, and there is no web/ to build it from"
            )
        build_data["artifacts"].append("src/wayfarer/static/")


def _run_pnpm(cwd: Path, *args: str) -> None:
    pnpm = shutil.which("pnpm")
    command = [pnpm] if pnpm else ["corepack", "pnpm"]
    env = {**os.environ, "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0"}
    subprocess.run([*command, *args], cwd=cwd, env=env, check=True)
