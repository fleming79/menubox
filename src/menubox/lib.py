from __future__ import annotations

from typing import TYPE_CHECKING

import ipywidgets as ipw

import menubox as mb
from menubox.defaults import hookimpl

if TYPE_CHECKING:
    from menubox.instance import IHPSettings, InstanceHP


@hookimpl
def instancehp_finalize_settings(inst: InstanceHP, klass: type, settings: IHPSettings):
    """

    - Setting default settings based on the class.
    - Handling specific cases for different widget types (e.g., Button, HasParent, DOMWidget).
    - Removing unnecessary settings.
    - Setting flags for loading defaults, allowing None values, and read-only mode.
    """
    s = settings
    if getattr(klass, "KEEP_ALIVE", False):
        s["on_replace_close"] = False
    if "on_replace_close" not in s:
        if issubclass(klass, mb.HasParent):
            s["on_replace_close"] = not klass.SINGLETON_BY
        elif issubclass(klass, ipw.Widget) and "on_replace_close":
            s["on_replace_close"] = True
    if issubclass(klass, ipw.Button) and not issubclass(klass, mb.async_run_button.AsyncRunButton):
        if "on_click" not in s:
            s["on_click"] = "button_clicked"
        else:
            s.pop("on_click", None)
    if not issubclass(klass, ipw.DOMWidget) or not s.get("add_css_class"):
        s.pop("add_css_class", None)
    if issubclass(klass, mb.HasParent) and "set_parent" not in s:
        s["set_parent"] = True
    inst.load_default = s.pop("load_default", inst.load_default)
    inst.allow_none = s.pop("allow_none", not inst.load_default)
    inst.read_only = s.pop("read_only", True)
