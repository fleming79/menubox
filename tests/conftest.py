from __future__ import annotations

from typing import TYPE_CHECKING

import async_kernel
import ipylab.ipylab
import ipylab.log
import ipywidgets as ipw
import pytest
from async_kernel import Caller
from async_kernel.utils import LAUNCHED_BY_DEBUGPY
from ipylab import JupyterFrontEnd

import menubox as mb

if TYPE_CHECKING:
    import pathlib


@pytest.fixture(scope="session")
def anyio_backend():
    if not LAUNCHED_BY_DEBUGPY:
        app = ipylab.JupyterFrontEnd()
        app.log_level = ipylab.log.LogLevel.WARNING
    else:
        mb.log.START_DEBUG(to_stdio=True)
    return "asyncio"


@pytest.fixture(scope="session")
async def kernel(anyio_backend):
    async with async_kernel.Kernel() as kernel:
        yield kernel


@pytest.fixture
async def caller(kernel: async_kernel.Kernel) -> Caller:
    return kernel.caller


@pytest.fixture
async def app(kernel: async_kernel.Kernel, mocker) -> JupyterFrontEnd:
    app = ipylab.JupyterFrontEnd()
    ipylab.ipylab.WAIT_READY = False
    app.set_trait("_vpath", "testing_vpath")
    mocker.patch.object(app, "wait_ready")
    return app


@pytest.fixture(autouse=True)
async def anyio_backend_autouse(app):
    return


@pytest.fixture
def weakref_enabled():
    ipw.enable_weakreference()
    yield None
    ipw.disable_weakreference()


@pytest.fixture
async def home(tmp_path: pathlib.Path):
    """"""
    url = tmp_path.as_posix()
    home = mb.Home(tmp_path.name)
    await home.filesystem
    home.filesystem.value = {"url": url}
    assert home.filesystem.url.value == url
    assert home.filesystem.home_url == url
    yield home
    home.close()
