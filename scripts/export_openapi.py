from __future__ import annotations

import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
backend_root = repo_root / "backend"
sys.path.insert(0, str(backend_root / "src"))

from mindmate.main import app


output = repo_root / "docs" / "openapi" / "openapi.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"OpenAPI {app.openapi()['openapi']} exported to {output.relative_to(repo_root)}")
