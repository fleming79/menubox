# SPDX-FileCopyrightText: 2025-present
#
# SPDX-License-Identifier: MIT


from menubox import (
    async_run_button,
    defaults,
    hasparent,
    instance,
    log,
    mb_async,
    menuboxvt,  # noqa: F401
    pack,
    trait_types,
    utils,
    valuetraits,
    widget_loader,
    widgets,
)
from menubox.__about__ import __version__
from menubox.defaults import hookimpl
from menubox.hasparent import HasParent
from menubox.home import Home
from menubox.mb_async import TaskType, debounce, throttle
from menubox.menubox import MenuBox
from menubox.menuboxvt import MenuBoxVT
from menubox.modalbox import ModalBox
from menubox.stylesheet import MenuboxStylesheet
from menubox.trait_types import Bunched, ChangeType, NameTuple, ProposalType, StrTuple, TypedTuple
from menubox.valuetraits import TypedInstanceTuple, ValueTraits

VERSION_INFO = {"menubox": __version__}
DEBUG_ENABLED = False


__all__ = [
    "async_run_button",
    "debounce",
    "throttle",
    "defaults",
    "hasparent",
    "instance",
    "log",
    "mb_async",
    "pack",
    "valuetraits",
    "trait_types",
    "utils",
    "widget_loader",
    "widgets",
    "Bunched",
    "ChangeType",
    "HasParent",
    "Home",
    "MenuBox",
    "MenuBoxVT",
    "ModalBox",
    "NameTuple",
    "ProposalType",
    "StrTuple",
    "TaskType",
    "TypedInstanceTuple",
    "TypedTuple",
    "ValueTraits",
    "hookimpl",
]


def _get_plugin_manager():
    # Only to be run once here
    import pluggy

    from menubox import hookspecs, lib

    pm = pluggy.PluginManager("menubox")
    pm.add_hookspecs(hookspecs)
    pm.register(lib)
    pm.load_setuptools_entrypoints("menubox")
    return pm


plugin_manager = _get_plugin_manager()
stylesheet: MenuboxStylesheet = plugin_manager.hook.default_css_stylesheet()
del _get_plugin_manager
