from __future__ import annotations

import asyncio
import contextlib
import inspect
import weakref
from typing import TYPE_CHECKING

import ipywidgets as ipw
from ipywidgets import Widget
from traitlets import HasTraits

import menubox as mb
from menubox import HasParent, utils
from menubox.children_setter import ChildrenSetter
from menubox.css import STYLESHEET, CSScls
from menubox.defaults import hookimpl

if TYPE_CHECKING:
    from ipylab.css_stylesheet import CSSStyleSheet

    from menubox.instance import IHPChange, IHPSettings, InstanceHP, S, T


_on_click_register = weakref.WeakKeyDictionary()
inst_close_observers: dict[InstanceHP, weakref.WeakKeyDictionary[HasParent | Widget, dict]] = {}

stylesheet: CSSStyleSheet | None = None


@hookimpl
def add_css_stylesheet():
    return STYLESHEET, {
        "--jp-widgets-input-background-color": "var(--jp-input-background)",
        "--jp-widgets-input-focus-border-color": "var(--jp-input-active-border-color)",
        "--jp-widgets-input-border-width": "var(--jp-border-width)",
    }


@hookimpl
def instancehp_finalize(inst: InstanceHP, settings: IHPSettings, klass: type):  # noqa: ARG001
    if getattr(klass, "KEEP_ALIVE", False):
        settings["on_replace_close"] = False
    if "on_replace_close" not in settings:
        if issubclass(klass, HasParent):
            settings["on_replace_close"] = not klass.SINGLETON_BY
        elif issubclass(klass, Widget) and "on_replace_close":
            settings["on_replace_close"] = True
    if issubclass(klass, ipw.Button) and not issubclass(klass, mb.async_run_button.AsyncRunButton):
        if "on_click" not in settings:
            settings["on_click"] = "button_clicked"
        else:
            settings.pop("on_click", None)
    if "add_css_class" in settings and not issubclass(klass, ipw.DOMWidget):
        settings.pop("add_css_class", None)
    if issubclass(klass, HasParent) and "set_parent" not in settings:
        settings["set_parent"] = True
    if "remove_on_close" not in settings and issubclass(klass, HasParent | Widget):
        settings["remove_on_close"] = True


@hookimpl
def instancehp_default_kwgs(inst: InstanceHP[S, T], parent: S, kwgs: dict):
    if inst.settings.get("set_parent"):
        kwgs["parent"] = parent

    if children := inst.settings.get("children"):
        if isinstance(children, dict):
            home = getattr(parent, "home", "_child setter")
            val = {} | children
            val.pop("mode")
            ChildrenSetter(home=home, parent=parent, name=inst.name, value=val)
        else:
            kwgs["children"] = parent.get_widgets(*children, skip_hidden=False, show=True)


@hookimpl
def instancehp_on_change(inst: InstanceHP, change: IHPChange):
    settings = inst.settings
    parent = change["parent"]
    old = change["old"]
    new = change["new"]
    for func in (on_replace_close, set_parent, dlink, remove_on_close, on_click, add_css_class):
        if func.__name__ in settings:
            try:
                func(inst, parent, old, new)
            except Exception as e:
                parent.on_error(e, str(func))
    if vc := settings.get("value_changed"):
        vc = getattr(parent, vc) if isinstance(vc, str) else vc
        vc(change)


def remove_on_close(inst: InstanceHP[S, T], parent: S, old: object | None, new: object | None):
    if parent.closed:
        return
    if inst not in inst_close_observers:
        inst_close_observers[inst] = weakref.WeakKeyDictionary()
    # value closed
    if (old_observer := inst_close_observers[inst].pop(parent, {})) and isinstance(old, HasParent | Widget):
        with contextlib.suppress(ValueError):
            old.unobserve(**old_observer)

    if isinstance(new, HasParent | Widget):
        parent_ref = weakref.ref(parent)

        def _observe_closed(change: mb.ChangeType):
            # If the parent has closed, remove it from parent if appropriate.
            parent = parent_ref()
            cname, value = change["name"], change["new"]
            if (
                parent
                and ((cname == "closed" and value) or (cname == "comm" and not value))
                and parent._trait_values.get(inst.name) is change["owner"]
            ) and (old := parent._trait_values.pop(inst.name, None)):
                inst._value_changed(parent, old, None)

        names = "closed" if isinstance(new, HasParent) else "comm"
        new.observe(_observe_closed, names)
        inst_close_observers[inst][parent] = {"handler": _observe_closed, "names": names}


def on_replace_close(inst: InstanceHP[S, T], parent: S, old: object | None, new: object | None):  # noqa: ARG001
    if inst.settings.get("on_replace_close") and isinstance(old, Widget | HasParent):
        if mb.DEBUG_ENABLED:
            parent.log.debug(f"Closing replaced item `{parent.__class__.__name__}.{inst.name}` {old.__class__}")
        old.close()


def on_click(inst: InstanceHP[S, T], parent: S, old: object | None, new: object | None):
    if on_click := inst.settings.get("on_click"):
        if isinstance(old, ipw.Button) and (on_click := _on_click_register.pop(old)):
            old.on_click(on_click, remove=True)
        if not parent.closed and isinstance(new, ipw.Button):
            if mb.DEBUG_ENABLED:
                if not callable(utils.getattr_nested(parent, on_click) if isinstance(on_click, str) else on_click):
                    msg = f"`{on_click=}` is not callable!"
                    raise TypeError(msg)
                if on_click == "button_clicked" and not asyncio.iscoroutinefunction(parent.button_clicked):
                    msg = f"By convention `{utils.fullname(new)}.button_clicked` must be a coroutine function!"
                    raise TypeError(msg)
            taskname = f"button_clicked[{id(new)}] → {parent.__class__.__qualname__}.{inst.name}"
            if new in _on_click_register:
                msg = "The button {} is already registered!"
                raise RuntimeError(msg)
            ref = weakref.ref(parent)

            def _on_click(b: ipw.Button):
                obj: S | None = ref()
                if obj:

                    async def click_callback():
                        callback = utils.getattr_nested(obj, on_click) if isinstance(on_click, str) else on_click
                        try:
                            b.add_class(CSScls.button_is_busy)
                            result = callback(b)
                            if inspect.isawaitable(result):
                                await result
                        finally:
                            b.remove_class(CSScls.button_is_busy)

                    mb.mb_async.run_async(click_callback, name=taskname, obj=obj)

            new.on_click(_on_click)
            _on_click_register[new] = _on_click


def dlink(inst: InstanceHP[S, T], parent: S, old: object | None, new: object | None):  # noqa: ARG001
    """Creates dynamic links (dlinks) between traits of objects based on the provided configuration.

    This function establishes links between a source trait of an object (typically a parent) and a target trait of another object,
    allowing changes in the source trait to propagate to the target trait. The links are configured based on the `dlink` setting
    associated with the given `InstanceHP` object.

    Args:
        inst (InstanceHP): The InstanceHP object containing the settings for the dynamic link.  The settings should include
            a "dlink" key that specifies the source and target traits to link.
        change (IHPChange): A dictionary containing information about the change that triggered the dlink creation.
            It should include the 'parent' object (where the source trait resides) and the 'new' object (where the target trait resides).

    The `dlink` setting can be a single dictionary or a list of dictionaries, each defining a dynamic link.
    Each dictionary should contain the following keys:

        - `source`: A tuple containing the name of the source object and the name of the source trait.
          If the source object name is "self", it refers to the `parent` object. Otherwise, it's an attribute of the parent.
        - `target`: The name of the target trait.  It can optionally include a class name prefix (e.g., "ClassName.trait_name")
           to specify a nested object within the target object.
        - `transform` (optional): A callable that transforms the value of the source trait before it is applied to the target trait.
          It can also be a string representing an attribute of the parent object that is a callable.

    The function uses the `dlink` method of the parent object to create the dynamic links. It first disconnects previous dlinks.
    Then, if the target object is a `HasTraits` instance, it creates a connected link to propagate changes to the target trait.

    Raises:
        TypeError: If the `transform` value is not callable.
    """
    if dlink := inst.settings.get("dlink"):
        dlinks = (dlink,) if isinstance(dlink, dict) else dlink
        for dlink in dlinks:
            src_name, src_trait = dlink["source"]
            src_obj = parent if src_name == "self" else utils.getattr_nested(parent, src_name, hastrait_value=False)
            tgt_trait = dlink["target"]
            key = f"{id(parent)} {parent.__class__.__qualname__}.{inst.name}.{tgt_trait}"
            if new and "." in tgt_trait:
                class_name, tgt_trait = tgt_trait.rsplit(".", maxsplit=1)
                new = utils.getattr_nested(new, class_name, hastrait_value=False)
            transform = dlink.get("transform")
            if isinstance(transform, str):
                transform = utils.getattr_nested(parent, transform, hastrait_value=False)
            if transform and not callable(transform):
                msg = f"Transform must be callable but got {transform:!r}"
                raise TypeError(msg)
            parent.dlink((src_obj, src_trait), target=None, transform=transform, key=key, connect=False)
            if not parent.closed and isinstance(new, HasTraits):
                parent.dlink((src_obj, src_trait), target=(new, tgt_trait), transform=transform, key=key)


def add_css_class(inst: InstanceHP[S, T], parent: S, old: object | None, new: object | None):  # noqa: ARG001
    if add_css_class := inst.settings.get("add_css_class"):
        for cn in utils.iterflatten(add_css_class):
            if isinstance(new, ipw.DOMWidget):
                new.add_class(cn)
            if isinstance(old, ipw.DOMWidget):
                old.remove_class(cn)


def set_parent(inst: InstanceHP[S, T], parent: S, old: object | None, new: object | None):
    if inst.settings.get("set_parent"):
        if isinstance(old, HasParent) and getattr(old, "parent", None) is parent:
            old.parent = None
        if isinstance(new, HasParent) and not parent.closed:
            new.parent = parent
