from __future__ import annotations

from typing import TYPE_CHECKING

import ipylab
from ipywidgets import Widget

import menubox as mb
from menubox import HasParent
from menubox.css import STYLESHEET
from menubox.defaults import hookimpl
from menubox.instance import InstanceHP

if TYPE_CHECKING:
    from ipylab.css_stylesheet import CSSStyleSheet

    from menubox.instance import IHPHookMappings, InstanceHP, S, T


stylesheet: CSSStyleSheet | None = None


@hookimpl
def add_css_stylesheet():
    return STYLESHEET, {
        "--jp-widgets-input-background-color": "var(--jp-input-background)",
        "--jp-widgets-input-focus-border-color": "var(--jp-input-active-border-color)",
        "--jp-widgets-input-border-width": "var(--jp-border-width)",
    }


@hookimpl
def instancehp_finalize(inst: InstanceHP, hookmappings: IHPHookMappings, klass: type):
    if "children" in hookmappings:
        raise NotImplementedError(str(inst))
    if getattr(klass, "KEEP_ALIVE", False):
        hookmappings["on_replace_close"] = False
    if "on_replace_close" not in hookmappings:
        if issubclass(klass, HasParent):
            hookmappings["on_replace_close"] = not klass.SINGLE_BY
        elif issubclass(klass, Widget) and "on_replace_close":
            hookmappings["on_replace_close"] = True
    if issubclass(klass, HasParent) and "set_parent" not in hookmappings:
        hookmappings["set_parent"] = True
    if "remove_on_close" not in hookmappings and issubclass(klass, HasParent | Widget):
        hookmappings["remove_on_close"] = True


@hookimpl
def instancehp_default_kwgs(inst: InstanceHP[S, T, T], parent: S, kwgs: dict):
    if inst._hookmappings.get("set_parent"):
        kwgs["parent"] = parent


@hookimpl
def get_icon(obj: mb.Menubox):  # noqa: ARG001
    return ipylab.Icon()
