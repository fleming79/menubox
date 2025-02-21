from __future__ import annotations

import asyncio
import functools
import importlib
import inspect
import weakref
from collections.abc import Callable, Generator, Iterable
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, TypeVar

import ipylab
import ipylab.log
import ipywidgets as ipw
import pandas as pd
import toolz
import traitlets

import menubox as mb
from menubox.defaults import NO_DEFAULT

if TYPE_CHECKING:
    from menubox.hasparent import HasParent
    from menubox.trait_types import ChangeType


T = TypeVar("T")
R = TypeVar("R")

P = ParamSpec("P")

__all__ = [
    "add_remove_prefix",
    "add_remove_suffix",
    "getattr_nested",
    "setattr_nested",
    "fullname",
    "fstr",
    "limited_string",
    "tuple_discard",
    "tuple_add",
    "funcname",
    "sanatise_name",
    "sanatise_filename",
    "iterflatten",
    "weak_observe",
]


def limited_string(obj, max_len=100, suffix=" …", mode="start"):
    """Returns a string rep of obj of length up to max_len."""
    s = str(obj)
    if len(s) > max_len - len(suffix):
        if mode == "start":
            return str(s)[0:max_len] + suffix
        if mode == "end":
            return suffix + str(s)[0:max_len]
        msg = f"{mode=}"
        raise NotImplementedError(msg)
    return s


def tuple_discard(items, *values):
    "Return a tuple of items not containing values."
    return tuple(v for v in items if v not in values)


def tuple_add(items, *values, top=True):
    """Return a tuple of unique items plus values with values placed at the front or
    behind.
    """
    return tuple(toolz.unique((*values, *items)) if top else toolz.unique((*items, *values)))


def trait_tuple_add(*values, owner: traitlets.HasTraits, name: str, top=False):
    """Set like functionality for the tuple `owner.name`."""
    if isinstance(owner, traitlets.HasTraits) and name:
        current = getattr(owner, name)
        new = tuple_add(current, *values, top=top)
        if new != current:
            owner.set_trait(name, new)


def trait_tuple_discard(*values, owner: traitlets.HasTraits, name: str):
    """Set like functionality for the tuple `owner.name`."""
    if isinstance(owner, traitlets.HasTraits) and name:
        current = getattr(owner, name)
        new = tuple_discard(current, *values)
        if new != current:
            owner.set_trait(name, new)


# TODO: concat the callable when pass_change is True.
def weak_observe(
    obj: traitlets.HasTraits, method: Callable[P, R], names="value", pass_change=False, *args: P.args, **kwgs: P.kwargs
) -> Callable[[ChangeType], R]:
    """Observer trait names of obj using a weak method ref to method like a partial.

    pass_change: bool [False]
        The change provided in the method call.
    args & kwgs are passed to the method like a partial.
    """
    ref = weakref.WeakMethod(method)

    def handle(change: ChangeType) -> R:
        method_ = ref()
        if method_:
            if pass_change:
                return method_(*args, change=change, **kwgs)  # type:ignore
            return method_(*args, **kwgs)
        change["owner"].unobserve(handle, names=names)

        return None  # type: ignore

    obj.observe(handle, names=names)
    return handle


def add_remove_prefix(prefix: str, items: list, add=True):
    """Add or remove the prefix from the list of items."""
    items_new = []
    for i in items:
        item = i
        if add:
            if not item.startswith(prefix):
                item = prefix + item
        else:
            item = item.removeprefix(prefix)
        items_new.append(item)
    return items_new


def add_remove_suffix(suffix: str, items: list, add=True):
    """Add or remove the prefix from the list of items."""
    items_new = []
    for i in items:
        item = i
        if add:
            if not item.endswith(suffix):
                item = item + suffix
        else:
            item = item.removesuffix(suffix)
        items_new.append(item)
    return items_new


def getattr_nested(obj, name: str, default: Any = NO_DEFAULT, *, hastrait_value=True) -> Any:
    """Get a nested attribute using dotted notation in the name.

    Callable values will be evaluated recursively until a non-callable is returned.

    hastrait_value: bool
        If name is an instance of of HasTraits and it has a trait 'value'
        return obj.name.value
    """

    if "." in name:
        a, b = name.split(".", maxsplit=1)
        obj_ = getattr(obj, a)
        if obj_ is None:
            return None
        return getattr_nested(obj_, b, default=default, hastrait_value=hastrait_value)
    try:
        val = getattr(obj, name) if default is NO_DEFAULT else getattr(obj, name, default)
        if hastrait_value and isinstance(val, traitlets.HasTraits) and val.has_trait("value"):
            val = val.value  # type: ignore
            name = "value"
        if name == "value":
            while callable(val):
                val = val()
    except Exception:
        if default is not NO_DEFAULT:
            return default
        raise
    else:
        return val


def setattr_nested(
    obj: Any, name: str, value: Any, default_setter: Callable[[Any, str, Any], None] | None = None
) -> None:
    """Sets a nested attribute of an object.
    The attribute is specified as a string with dot notation, e.g. "foo.bar.baz".
    Args:
        obj: The object to set the attribute on.
        name: The name of the attribute to set, with dot notation for nested attributes.
        value: The value to set the attribute to.
        default_setter: A callable that takes the object, name, and value as arguments and sets the attribute.
            If not specified, the built-in `setattr` function is used.  If the object has a `setter` attribute,
            that is used in preference to `default_setter`.
    Raises:
        AttributeError: If the attribute cannot be set and DEBUG_ENABLED is False.
            The original exception is included in the AttributeError as the cause.
            If DEBUG_ENABLED is True, the original exception is raised.
    """
    bits = name.split(".")
    if len(bits) > 1:
        obj = getattr(obj, bits[0])
        setattr_nested(obj, ".".join(bits[1:]), value, default_setter=default_setter)
    else:
        try:
            setter = getattr(obj, "setter", None) or default_setter or setattr
            setter(obj, name, value)
        except Exception as e:
            import menubox

            if menubox.DEBUG_ENABLED:
                raise
            msg = f"Failed to set nested attribute: {fullname(obj)}.{name} = {limited_string(value)}"
            raise AttributeError(msg) from e


def load_nested_attrs(
    obj,
    values: dict | Callable[[], dict],
    raise_errors: bool = True,  # noqa: FBT001
    default_setter: Callable[[Any, str, Any], None] = setattr,
    on_error: Callable[[Exception, str, Any], None] | None = None,
) -> dict[str, Any]:
    """Loads nested attributes into an object using `setattr_nested` from a dictionary or a callable that returns a dictionary.

    Args:
        obj: The object to load attributes into.
        values: A dictionary containing attribute-value pairs, or a callable that returns such a dictionary.
        raise_errors: If True, raise an exception if an error occurs while setting an attribute.
        default_setter: The function to use for setting attributes. Defaults to `setattr`.
        on_error: An optional callback function to handle errors.  It receives the exception,
            a message, and the object as arguments. If not provided, `mb.log.on_error` is used.
    Returns:
        A dictionary containing the attributes that were successfully set.
    Raises:
        AttributeError: If `values` is not a dictionary and not callable, and `raise_errors` is True.
        Any exception raised by `setattr_nested` if setting an attribute fails and `raise_errors` is True.
    """

    while callable(values):
        values = values()
    if not isinstance(values, dict):
        if raise_errors:
            msg = f"values is not a dict {type(values)}="
            raise AttributeError(msg)
        return {}
    kwn = {}
    for attr, value in values.items():
        try:
            setattr_nested(obj, attr, value, default_setter=default_setter)
            kwn[attr] = value
        except Exception as e:
            msg = f"Could not set nested attribute:  {fullname(obj)}.{attr} = {limited_string(value)} --> {e}"
            if not on_error:
                on_error = mb.log.on_error
            on_error(e, msg, obj)
            if raise_errors:
                raise
    return kwn


def fullname(obj) -> str:
    """Return the full name (module + class name) of an object."""
    if hasattr(obj, "__wrapped__"):
        return fullname(obj.__wrapped__)
    try:
        if inspect.ismethod(obj):
            return f"{fullname(obj.__self__)}.{funcname(obj)}"
        if callable(obj):
            return f"{obj.__module__}.{funcname(obj)}"
        if inspect.isawaitable(obj):
            return funcname(obj)
        if isinstance(obj, traitlets.MetaHasTraits):
            return f"{obj.__module__}.{obj.__qualname__}"
        module = obj.__class__.__module__
        if module is None or module == str.__class__.__module__:
            return obj.__class__.__qualname__
    except Exception:
        return str(obj)
    else:
        return f"{module}.{obj.__class__.__qualname__}"


def funcname(obj: Any) -> str:
    """Get function name for a callable or task.

    Known to work for standard functions, methods and functools.partial
    """
    if hasattr(obj, "__wrapped__"):
        return funcname(obj.__wrapped__)
    if isinstance(obj, mb.mb_async._Periodic):
        return funcname(obj.wrapped)
    if not callable(obj) and not inspect.isawaitable(obj):
        msg = f"{fullname(obj)} is not callable"
        raise TypeError(msg)
    try:
        if asyncio.isfuture(obj):
            try:
                return obj._coro.__qualname__  # type: ignore
            except Exception:
                return obj.__class__.__qualname__
        try:
            return obj.func.__qualname__  # type: ignore
        except AttributeError:
            return obj.__qualname__  # type: ignore
    except Exception:
        return str(obj)


def fstr(template: str, raise_errors=False, **globals) -> str:  # noqa: A002
    """Evaluate the fstring template with the mapped globals.

    The template must not contain triple quote `'''`.
    """
    try:
        return eval(f"f''' {template} '''", globals)[1:-1]  # noqa: S307
    except Exception as e:
        if template.find("'''") >= 0:
            template = template.replace("'''", '"""')
            return fstr(template, raise_errors=raise_errors, **globals)[1:-1]
        if raise_errors:
            msg = f"An error occurred evaluating the string '{template}' "
            raise RuntimeError(msg) from e
        return template


def sanatise_name(name: str, allow=" _", strip=" ", lstrip="012345679-", replace="", allow_space=True) -> str:
    """Sanatises a string to be used as a name.

    Args:
        name (str): The string to sanatise.
        allow (str, optional): Additional characters to allow in the name. Defaults to " _".
        strip (str, optional): Characters to strip from the beginning and end of the name. Defaults to " ".
        lstrip (str, optional): Characters to strip from the beginning of the name. Defaults to "0123456789-".
        replace (str, optional): Character to replace disallowed characters with. Defaults to "".
        allow_space (bool, optional): Whether to allow spaces in the name. Defaults to True.

    Returns:
        str: The sanatised name.
    """
    return (
        "".join(
            c if ((c.isalpha() or c.isdigit() or c in allow) and (allow_space or not c.isspace())) else replace
            for c in name
        )
        .strip(strip)
        .lstrip(lstrip)
    )


def stem(path: str):
    """Access the 'stem' from a filename.

    Args:
        path (str): a typical path.
    """
    return splitname(path)[-1].rsplit(".", maxsplit=1)[0]


def splitname(path: str):
    """Split a path into the root / name

    Args:
        path (str): a typical path.
    """
    parts = joinpaths(path).rsplit("/", maxsplit=1)
    return ["", parts[0]] if len(parts) == 1 else parts


def joinpaths(*parts):
    """Join arbitrary path and convert to posix style.

    The first part is expected to be a proper root, and only end with a slash
    if it is a root folder.

    Note: this will strip trailing slashes.
    """
    return "/".join(pp for p in iterflatten(parts) if p and (pp := str(p).replace("\\", "/").rstrip("/")))


sanatise_filename = functools.partial(sanatise_name, allow=" \\/_==-.,~!@#$%^&()[]{}", lstrip="", replace="_")


def iterflatten(iterable: Iterable[T]) -> Generator[T, None, None]:
    """An iterator flattening everything except strings."""
    if isinstance(iterable, str):
        yield iterable  # type: ignore
    else:
        try:
            for e in iterable:
                if isinstance(iterable, str):
                    yield e
                yield from iterflatten(e)  # type: ignore
        except TypeError:
            yield iterable  # type: ignore


GetWidgetsInputType = None | str | Callable | ipw.Widget | Iterable[str | Callable | ipw.Widget | None]


def get_widgets(
    *items: GetWidgetsInputType,
    skip_disabled=False,
    skip_hidden=True,
    show=True,
    parent: HasParent | None = None,
) -> Generator[ipw.Widget, None, None]:
    """Collects widgets omitting duplicate side-by-side instances and self.

    Accepts widgets, dotted name attributes and callables that returns one or
    more widgets. Nested lists/tuples are flattened accordingly.

    Note: It doesn't instantiate widgets.

    items: tuple str | Callable | ipw.Widget


    * names of attributes eg. self.attribute.subwidget  as "attribute.subwidget"
    * "H_FILL" & "V_FILL" are special names that provide a box configured according.
    * callable that returns a widget or list of widgets
    * widgets
    * fstr style strings  starting with {  eg. "{self.__class__}"
    """
    last_widget: ipw.Widget | None = None

    def _get_widgets(items):
        for item in iterflatten(items):
            nonlocal last_widget
            widget = item
            try:
                while callable(widget):
                    widget = widget()
                if isinstance(widget, str):
                    match widget:
                        case "H_FILL":
                            widget = mb.defaults.H_FILL
                        case "V_FILL":
                            widget = mb.defaults.V_FILL
                        case _:
                            widget = getattr_nested(parent, widget, None, hastrait_value=False)
                if widget is None:
                    continue
                if isinstance(widget, ipw.Widget):
                    if (
                        getattr(widget, "_repr_mimebundle_", None)  # Not closed
                        and widget.comm  # closed
                        and widget is not parent  # Would likely causes browser to crash with recursion.
                        and last_widget is not widget  # Skip side-by-side
                        and not (skip_hidden and hasattr(widget, "layout") and widget.layout.visibility == "hidden")  # type: ignore
                        and not (skip_disabled and getattr(widget, "disabled", False))
                    ):
                        if (panel := getattr(widget, "panel", None)) and isinstance(panel, ipylab.Panel):
                            widget = panel
                        yield widget
                        last_widget = widget
                        if show and not hasattr(widget, "layout") or (widget.layout, "visibility", "") != "hidden":  # type: ignore
                            show_ = getattr(widget, "show", None)
                            if callable(show_):
                                show_()
                else:
                    yield from _get_widgets(widget)
            except TypeError:
                continue
            except RecursionError:
                raise
            except Exception as e:
                msg = f"An exception occurred getting {widget=}. It will be omitted from the list of widgets."
                if parent:
                    parent.on_error(e, msg, widget)
                else:
                    ipylab.app.log.exception(e, msg, widget)

    yield from _get_widgets(items)


def hide(widget):
    """Hide the widget."""
    if hasattr(widget, "layout"):
        widget.layout.visibility = "hidden"


def unhide(widget):
    """Unhide the widget."""
    if hasattr(widget, "layout"):
        widget.layout.visibility = "visible"


def set_border(widget, border: str = "solid 1px black"):
    """Set the layout of the widget."""

    widget.layout.border = border


def to_visibility(f, invert=False):
    """Returns either 'visible' if True else 'hidden'.

    invert:
        invert the result.
    Attempts a few transforms.
    """
    if callable(f):
        f = f()
    if isinstance(f, pd.DataFrame):
        f = not f.empty
    if invert:
        f = not f
    if f:
        return "visible"
    return "hidden"


def to_hidden(f):
    """to_visibility inverted."""
    return to_visibility(f, invert=True)


def obj_is_in_box(obj, box: ipw.Box | None) -> ipw.Widget | None:
    """Complements show_obj_in_box.

    Returns either the obj, its wrapper or None if it wasn't put in the box using
    the function show_obj_in box.
    """
    if not box:
        return None
    for c in box.children:
        if c is obj or isinstance(c, mb.MenuBox) and c.views.get("WRAPPED") is obj:
            return c
    return None


def show_obj_in_box(
    obj: ipw.Widget | mb.MenuBox,
    box: ipw.Box,
    *,
    button_exit=True,
    button_promote=True,
    button_demote=True,
    top=True,
    alt_name="",
    border="solid 1px LightGrey",
) -> mb.MenuBox:
    """Add obj to box.children, if it isn't a menubox, wrap it in one first.

    If obj is in the box already it will be moved to top (or bottom).
    """
    if isinstance(obj, mb.MenuBox) and obj.closed:
        msg = f"The instance of {fullname(obj)} is closed!"
        raise RuntimeError(msg)
    if not isinstance(obj, ipw.Widget):
        msg = f"obj of type={type(obj)} is not a widget!"
        raise TypeError(msg)
    # Check if obj is already in the box or wrapped in a box
    exists = obj_is_in_box(obj, box)
    if exists:
        if not isinstance(exists, mb.MenuBox):
            msg = "Bug above"
            raise RuntimeError(msg)
        obj = exists
    if not isinstance(obj, mb.MenuBox):
        obj = mb.MenuBox(name=alt_name, views={"WRAPPED": obj}, view="WRAPPED")
        if alt_name:
            obj.title_description = "<b>{self.name}<b>"
    children = tuple_add(box.children, obj, top=top)
    box.children = tuple(c for c in children if getattr(c, "_repr_mimebundle_", None))
    if obj.showbox is not box:
        obj.set_trait("showbox", None)
    obj.set_trait("showbox", box)
    obj.instanceHP_enable_disable("button_exit", button_exit)
    obj.instanceHP_enable_disable("button_promote", button_promote)
    obj.instanceHP_enable_disable("button_demote", button_demote)
    if not obj.layout.border and not getattr(obj, "DEFAULT_BORDER", ""):
        obj.set_border(border)
    obj.show(unhide=True)
    return obj


def move_item(items: tuple, item, direction: Literal[-1, 1]):
    """Move an item within a tuple.

    This function moves a specified item within a tuple forward or backward,
    effectively changing its position in the tuple.
    The movement is circular, meaning that moving an item past the
    beginning or end of the tuple will wrap it around to the other side.
    Args:
        items (tuple): A tuple of ipywidgets widgets.
        item (ipw.Widget): The widget to move.
        direction (int): The direction to move the widget.
            1: moves the widget forward.
           -1: moves it backward.
    Returns:
        tuple: A new tuple with the item moved to its new position.
    """
    items_ = list(items)
    idx = items_.index(item)
    new_idx = idx + direction

    if 0 <= new_idx < len(items_):
        items_ = list(items_)  # Convert to list for mutability
        items_.insert(new_idx, items_.pop(idx))
    elif new_idx < 0:
        items_.append(items_.pop(idx))
    else:
        items_.insert(0, items_.pop(idx))
    return tuple(items_)


def download_button(buffer, filename: str, button_description: str):
    """Loads data from file f into base64 payload embedded into a HTML button.
    Recommended for small files only.

    buffer: open file object ready for reading.
        A file like object with a read method.
    filename:    str
        The name when it is downloaded.
    button_description: str
        The text that goes into the button.
    """
    import base64

    payload = base64.b64encode(buffer.read()).decode()

    html_button = f"""<html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    </head>
    <body>
    <a download="{filename}" href="data:text/csv;base64,{payload}">
    <button class="p-Widget jupyter-widgets jupyter-button widget-button mod-warning">
    {button_description}</button>
    </a>
    </body>
    </html>
    """
    return ipw.HTML(html_button)


def import_item(dottedname: str):
    """Import an item from a module, given its dotted name.

    For example:
    >>> import_item("os.path.join")
    """
    modulename, objname = dottedname.rsplit(".", maxsplit=1)
    return getattr(importlib.import_module(modulename), objname)
