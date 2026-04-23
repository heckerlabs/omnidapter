"""Export the omnidapter-server OpenAPI spec to openapi/openapi.json.

Paths excluded from the SDK (connect UI, oauth callbacks, health) are
stripped from the output so OpenAPI Generator only sees SDK-facing routes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("OMNIDAPTER_ENV", "LOCAL")

from omnidapter_server.main import create_app  # noqa: E402

OUTFILE = Path(__file__).parent.parent / "openapi" / "openapi.json"

EXCLUDED_PREFIXES = ("/connect/", "/oauth/", "/health")


def main() -> None:
    app = create_app()
    spec = app.openapi()

    spec["paths"] = {
        path: methods
        for path, methods in spec["paths"].items()
        if not any(path.startswith(p) for p in EXCLUDED_PREFIXES)
    }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    OUTFILE.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"✓ Exported OpenAPI spec to {OUTFILE}")


if __name__ == "__main__":
    main()
