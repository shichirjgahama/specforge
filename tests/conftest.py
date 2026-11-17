import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from specforge.core.nodes import build_index
from specforge.core.parser import parse
from specforge.core.semantic import analyze
from specforge.core.validator import validate
from specforge.runtime.codegen import generate_tests
from specforge.services import SpecForgeService

SPEC_PATH = ROOT / "specs" / "scooter_share.sforge"


@pytest.fixture(scope="session")
def spec_source() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def program(spec_source):
    return parse(spec_source, str(SPEC_PATH)).program


@pytest.fixture(scope="session")
def semantic(program):
    return analyze(program)


@pytest.fixture(scope="session")
def index(program, semantic):
    return build_index(program, semantic.model)


@pytest.fixture(scope="session")
def validation(semantic, index):
    return validate(semantic, index)


@pytest.fixture(scope="session")
def cases(program, index):
    return generate_tests(program, index)


@pytest.fixture
def service(tmp_path):
    return SpecForgeService(db_path=tmp_path / "specforge.db",
                            spec_path=SPEC_PATH)
