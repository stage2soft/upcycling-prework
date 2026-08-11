from __future__ import annotations

import os
from pathlib import Path
import tempfile


TEST_ROOT = Path(tempfile.mkdtemp(prefix="prework-tests-"))
DATA_ROOT = TEST_ROOT / "data-root"
DATA_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["DATA_ROOT_PATH"] = str(DATA_ROOT)
os.environ["HOST_DATA_ROOT_PATH"] = str(DATA_ROOT)
for name, env_name in (
    ("selected", "SELECTED_DATA_PATH"),
    ("app-data", "APP_DATA_PATH"),
):
    path = TEST_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    os.environ[env_name] = str(path)
    os.environ[f"HOST_{env_name}"] = str(path)
