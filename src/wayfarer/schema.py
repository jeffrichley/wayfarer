"""Print the OpenAPI schema the browser's types are generated from.

`python -m wayfarer.schema > openapi.json`, run by `pnpm gen:types` in `web/`.
"""

from __future__ import annotations

import json
from pathlib import Path

from wayfarer.app import create_app

if __name__ == "__main__":
    print(json.dumps(create_app(Path.cwd()).openapi(), indent=2, sort_keys=True))
