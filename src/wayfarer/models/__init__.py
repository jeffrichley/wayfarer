"""Every shape that crosses to the browser, defined once.

FastAPI publishes these as OpenAPI, and `web/src/api.gen.ts` is generated from
that schema (`pnpm gen:types`), so the browser's types never drift from these
(ADR-0004).

One module per area, each listing its shapes in `__all__`, and each re-exported
here by one line, so every shape is reachable from `wayfarer.models`. The lines
stay sorted: two tickets adding areas then insert at different places, not both
at the end (#92). `tests/test_the_schema.py` fails for a shape in any module
here that is missing from the schema or from this package.

Each Needs you item lives with the area that raises it, `ShipEffort` with the
cascade and `EnvironmentFailure` with the gate, whose `GateStatus` names the one
it raised; the list that orders them all lives with home, which shows it.
"""

from wayfarer.models.asking import *
from wayfarer.models.cascade import *
from wayfarer.models.chronicle import *
from wayfarer.models.desk import *
from wayfarer.models.gate import *
from wayfarer.models.graph import *
from wayfarer.models.health import *
from wayfarer.models.home import *
from wayfarer.models.image import *
from wayfarer.models.read_model import *
from wayfarer.models.restart import *
from wayfarer.models.sessions import *
from wayfarer.models.stream import *
