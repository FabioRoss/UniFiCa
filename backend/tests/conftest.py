import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture()
def db(tmp_path):
    from app.db import SessionLocal, init_engine

    init_engine(tmp_path / "test.db")
    s = SessionLocal()
    yield s
    s.close()
