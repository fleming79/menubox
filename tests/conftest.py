import ipywidgets as ipw
import pytest


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def anyio_backend_autouse(anyio_backend):
    return anyio_backend


@pytest.fixture(autouse=True)
def weakref_enabled():
    ipw.enable_weakreference()
    yield None
    ipw.disable_weakreference()
