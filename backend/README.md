# MindMate AI Backend

Python 3.12 + FastAPI local service. The service is intentionally small during stage 0 and exposes only system endpoints:

- `GET /api/v1/health`
- `GET /api/v1/ready`
- `GET /api/v1/version`
- `GET /openapi.json`

Install and run from PowerShell:

```powershell
uv sync --dev
uv run uvicorn mindmate.main:app --host 127.0.0.1 --port 8000 --reload
```

Real Provider calls and credentials are not part of stage 0. Use Mock Provider infrastructure in later stages.
