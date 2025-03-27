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
from menubox.hasparent import HasHome, HasParent, Home, Parent
from menubox.mb_async import TaskType, debounce, throttle
from menubox.menubox import Menubox
from menubox.menuboxvt import MenuboxVT, MenuboxVTH
from menubox.modalbox import Modalbox
from menubox.trait_types import Bunched, ChangeType, FromParent, NameTuple, ProposalType, StrTuple, TypedTuple
from menubox.valuetraits import InstanceHPTuple, ValueTraits

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
    "FromParent",
    "Home",
    "HasHome",
    "Menubox",
    "MenuboxVT",
    "MenuboxVTH",
    "Modalbox",
    "NameTuple",
    "Parent",
    "ProposalType",
    "StrTuple",
    "TaskType",
    "InstanceHPTuple",
    "TypedTuple",
    "ValueTraits",
    "hookimpl",
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
