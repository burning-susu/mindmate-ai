$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot\..
uv run pyinstaller --noconfirm --clean --onedir --name mindmate-stage1 --paths src --add-binary ".venv/Lib/site-packages/sqlite_vec/vec0.dll;sqlite_vec" spikes/pyinstaller_entry.py
Pop-Location
