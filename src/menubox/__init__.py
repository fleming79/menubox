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
from menubox.hashome import HasHome, Home
from menubox.hasparent import HasParent
from menubox.instancehp_tuple import InstanceHPTuple
from menubox.mb_async import TaskType, debounce, throttle
from menubox.menubox import Menubox
from menubox.menuboxvt import MenuboxVT
from menubox.modalbox import Modalbox
from menubox.trait_types import Bunched, ChangeType, NameTuple, ProposalType, StrTuple, TypedTuple
from menubox.valuetraits import ValueTraits

VERSION_INFO = {"menubox": __version__}
DEBUG_ENABLED = False


__all__ = [
    "Bunched",
    "ChangeType",
    "HasHome",
    "HasParent",
    "Home",
    "InstanceHPTuple",
    "Menubox",
    "MenuboxVT",
    "Modalbox",
    "NameTuple",
    "ProposalType",
    "StrTuple",
    "TaskType",
    "TypedTuple",
    "ValueTraits",
    "async_run_button",
    "debounce",
    "defaults",
    "hasparent",
    "hookimpl",
    "instance",
    "log",
    "mb_async",
    "pack",
    "throttle",
    "trait_types",
    "utils",
    "valuetraits",
    "widget_loader",
    "widgets",
]


def _get_plugin_manager():
    # Only to be run once here
    import ipylab
    import pluggy

    from menubox._autostart import IpylabPlugin

    ipylab.plugin_manager.register(IpylabPlugin(), name="menubox")

    from menubox import hookspecs, lib

    pm = pluggy.PluginManager("menubox")
    pm.add_hookspecs(hookspecs)
    pm.register(lib)
    return pm


plugin_manager = _get_plugin_manager()
del _get_plugin_manager
