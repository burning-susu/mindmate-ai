# These imports keep the native AI dependencies visible to the packaging spike.
import keyring  # noqa: F401
import onnxruntime  # noqa: F401
import sqlite_vec  # noqa: F401
import uvicorn

from mindmate.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=0)
