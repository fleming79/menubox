from __future__ import annotations

from typing import TYPE_CHECKING

import ipylab.log
import ipywidgets as ipw
import pytest
from async_kernel import Caller
from async_kernel.utils import LAUNCHED_BY_DEBUGPY

import menubox as mb

if TYPE_CHECKING:
    import pathlib


@pytest.fixture(scope="session")
def anyio_backend():
    if not LAUNCHED_BY_DEBUGPY:
        app = ipylab.App()
        app.log_level = ipylab.log.LogLevel.WARNING
    else:
        mb.log.START_DEBUG(to_stdio=True)
    return "asyncio"


@pytest.fixture(autouse=True)
async def anyio_backend_autouse(anyio_backend, mocker):
    app = ipylab.App()
    async with Caller(create=True):
        mocker.patch.object(app, "ready")
        yield anyio_backend


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
