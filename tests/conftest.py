from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path

# Must happen before application module imports.
sys.path.insert(0, str(Path(__file__).parents[1]))
_DIR=Path(tempfile.mkdtemp(prefix="ledgerlens_test_"))
os.environ["DATABASE_URL"]="sqlite:///"+str(_DIR/"test.db")
os.environ["APP_API_KEY"]="fixture-test-secret"
os.environ.pop("OLLAMA_BASE_URL",None)

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine

@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c

@pytest.fixture
def auth():
    return {"X-API-Key":"fixture-test-secret"}

@pytest.fixture
def examples_dir():
    return Path(__file__).parents[1]/"examples"
