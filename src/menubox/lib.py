from __future__ import annotations

from typing import TYPE_CHECKING

import ipywidgets as ipw

import menubox as mb
from menubox.children_setter import ChildrenSetter
from menubox.defaults import hookimpl
from menubox.instance import IHPCreate

if TYPE_CHECKING:
    from menubox import HasParent
    from menubox.instance import IHPSettings, InstanceHP


@hookimpl
def instancehp_finalize_settings(inst: InstanceHP, klass: type, settings: IHPSettings):
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


@hookimpl
def instancehp_default_kwgs(inst: InstanceHP, parent: HasParent, kwgs: dict):
    if inst.settings.get("set_parent"):
        kwgs["parent"] = parent

    if dynamic_kwgs := inst.settings.get("dynamic_kwgs"):
        for name, value in dynamic_kwgs.items():
            if callable(value):
                kwgs[name] = value(
                    IHPCreate(parent=parent, name=inst.name, klass=inst.klass, args=inst.args, kwgs=kwgs)
                )
            elif value == "self":
                kwgs[name] = parent
            else:
                kwgs[name] = mb.utils.getattr_nested(parent, value, hastrait_value=False)

    if children := inst.settings.get("children"):
        if isinstance(children, dict):
            home = getattr(parent, "home", "_child setter")
            ChildrenSetter(home=home, parent=parent, name=inst.name, dottednames=children["dottednames"])
        else:
            kwgs["children"] = parent.get_widgets(*children, skip_hidden=False, show=True)


@hookimpl
def instancehp_default_create(inst: InstanceHP, parent: HasParent, args: tuple, kwgs: dict):
    create = inst.settings.get("create")
    if create:
        create = mb.utils.getattr_nested(parent, create, hastrait_value=False) if isinstance(create, str) else create
        return create(IHPCreate(parent=parent, name=inst.name, klass=inst.klass, args=args, kwgs=kwgs))
    return inst.klass(*args, **kwgs)
