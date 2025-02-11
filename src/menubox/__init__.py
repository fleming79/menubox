# SPDX-FileCopyrightText: 2025-present
#
# SPDX-License-Identifier: MIT


from menubox import defaults, hasparent, instance, log, pack, trait_types, utils, valuetraits, widget_loader, widgets
from menubox.__about__ import __version__
from menubox.hasparent import HasParent
from menubox.home import Home
from menubox.menubox import MenuBox
from menubox.menuboxvt import MenuBoxVT
from menubox.modalbox import ModalBox
from menubox.trait_types import Bunched, ChangeType, NameTuple, ProposalType, StrTuple, TypedTuple
from menubox.utils import TaskType
from menubox.valuetraits import TypedInstanceTuple, ValueTraits

VERSION_INFO = {"menubox": __version__}
DEBUG_ENABLED = False


__all__ = [
    "defaults",
    "hasparent",
    "instance",
    "log",
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
]
