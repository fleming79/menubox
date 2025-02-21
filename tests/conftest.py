from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import ipylab.log
import ipywidgets as ipw
import pytest

import menubox as mb

if TYPE_CHECKING:
    import pathlib


@pytest.fixture(scope="session")
def anyio_backend():
    mb.log.START_DEBUG(to_stdio=True)
    if "debugpy" not in sys.modules:
        ipylab.app.log_level = ipylab.log.LogLevel.WARNING
    return "asyncio"


@pytest.fixture(autouse=True)
async def anyio_backend_autouse(anyio_backend):
    return anyio_backend


@pytest.fixture
def weakref_enabled():
    ipw.enable_weakreference()
    yield None
    ipw.disable_weakreference()


@pytest.fixture
async def home(tmp_path: pathlib.Path):
    """"""
    return mb.Home(tmp_path)
