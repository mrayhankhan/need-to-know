import pytest

from ntk import access, db, seed


@pytest.fixture(scope="session", autouse=True)
def loaded():
    if not db.ping():
        pytest.skip("FalkorDB is not reachable (set FALKORDB_HOST/PORT)")
    seed.load_all()
    access.reset_cache()
    yield


@pytest.fixture()
def spec():
    return seed.build_spec("northwind")


@pytest.fixture()
def fresh():
    """Reload northwind before a test that changes the graph."""
    seed.load(seed.build_spec("northwind"))
    access.reset_cache()
    yield
    seed.load(seed.build_spec("northwind"))
    access.reset_cache()
