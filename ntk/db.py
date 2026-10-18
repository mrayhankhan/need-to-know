import threading

from falkordb import FalkorDB

from . import config

_lock = threading.Lock()
_client = None


def client() -> FalkorDB:
    global _client
    with _lock:
        if _client is None:
            _client = FalkorDB(
                host=config.FALKORDB_HOST,
                port=config.FALKORDB_PORT,
                username=config.FALKORDB_USERNAME,
                password=config.FALKORDB_PASSWORD,
            )
        return _client


def graph(name: str):
    return client().select_graph(name)


def tenant_graph(tenant: str):
    if tenant not in config.TENANTS:
        raise ValueError(f"unknown tenant: {tenant}")
    return graph(tenant)


def rows(g, q: str, params: dict | None = None, ro: bool = False) -> list:
    run = g.ro_query if ro else g.query
    return run(q, params or {}).result_set


def graph_names() -> list[str]:
    return client().list_graphs()


def ping() -> bool:
    try:
        client().connection.ping()
        return True
    except Exception:
        return False
