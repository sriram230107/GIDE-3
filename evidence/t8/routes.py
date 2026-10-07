"""T8: dump server API routes (no DB needed — imports only) for client/server parity."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "gide" / "services" / "api"))

from app.main import app  # noqa: E402

import json

from app.main import app  # noqa: E402

spec = app.openapi()
paths = spec["paths"]
print(len(paths))
for p in sorted(paths):
    print(",".join(sorted(paths[p])).upper(), p)
