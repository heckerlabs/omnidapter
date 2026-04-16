"""Export the omnidapter-server OpenAPI spec to fern/openapi/openapi.json."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("OMNIDAPTER_ENV", "LOCAL")

from omnidapter_server.main import create_app

OUTFILE = Path(__file__).parent.parent / "fern" / "openapi" / "openapi.json"


def main() -> None:
    app = create_app()
    spec = app.openapi()
    OUTFILE.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"✓ Exported OpenAPI spec to {OUTFILE}")


if __name__ == "__main__":
    main()
