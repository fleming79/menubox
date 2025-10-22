from __future__ import annotations

import asyncio
import datetime
import functools
import inspect
import weakref
from collections.abc import Callable, Generator, Iterable
from typing import TYPE_CHECKING, Any, Concatenate, Literal, overload

import ipylab
import ipylab.log
import ipywidgets as ipw
import pandas as pd
import traitlets
from async_kernel import AsyncEvent

import menubox as mb
from menubox.css import CSSvar
from menubox.defaults import NO_DEFAULT

if TYPE_CHECKING:
    from menubox.instance import S
    from menubox.trait_types import ChangeType, GetWidgetsInputType, P, T


__all__ = [
    "getattr_nested",
    "setattr_nested",
    "fullname",
    "fstr",
    "limited_string",
    "funcname",
    "sanatise_name",
    "sanatise_filename",
    "iterflatten",
    "weak_observe",
    "observe_once",
    "observe_until",
    "wait_trait_value",
    "yes_no_dialog",
    "now",
]


def limited_string(obj, max_len=100, suffix=" …", mode: Literal["start", "end"] = "start"):
    """Returns a string rep of obj of length up to max_len."""
    s = str(obj)
    if len(s) > max_len - len(suffix):
        if mode == "start":
            return str(s)[0:max_len] + suffix
        if mode == "end":
            return suffix + str(s)[-max_len:]
    return s


if TYPE_CHECKING:

    @overload
    def weak_observe(
        obj: traitlets.HasTraits,
        method: Callable[Concatenate[ChangeType, P], T],
        names: str = ...,
        pass_change: Literal[True] = True,
        *args: P.args,
        **kwgs: P.kwargs,
    ) -> Callable[[ChangeType], T]: ...
    @overload
    def weak_observe(
        obj: traitlets.HasTraits,
        method: Callable[P, T],
        names: str = ...,
        pass_change: Literal[False] = ...,
        *args: P.args,
        **kwgs: P.kwargs,
    ) -> Callable[[ChangeType], T]: ...


def weak_observe(
    obj: traitlets.HasTraits,
    method: Callable[P, T] | Callable[Concatenate[ChangeType, P], T],
    names="value",
    pass_change=False,
    *args: P.args,
    **kwgs: P.kwargs,
) -> Callable[[ChangeType], T]:
    """Observes a traitlet of an object using a weak reference to the callback method.

    This allows the observed object to be garbage collected even if the callback
    method is still referenced by the traitlet.
    Args:
        obj: The traitlets.HasTraits object to observe.
        method: The callback method to be called when the traitlet changes.
        names: The name(s) of the traitlet(s) to observe. Defaults to "value".
        pass_change: Whether to pass the change dictionary to the callback method. Defaults to False.
        *args: Positional arguments to be passed to the callback method.
        **kwgs: Keyword arguments to be passed to the callback method.
    Returns:
        The handle function that was registered as an observer, which can be used to unobserve.
    """

    ref = weakref.WeakMethod(method)

    def handle(change: ChangeType) -> T:
        method_ = ref()
        if method_:
            if pass_change:
                return method_(*args, change=change, **kwgs)  # type:ignore
            return method_(*args, **kwgs)  # type: ignore
        change["owner"].unobserve(handle, names=names)

        return None  # type: ignore

    obj.observe(handle, names=names)
    return handle


def observe_once(obj: traitlets.HasTraits, callback: Callable[[ChangeType], None], name: str):
    "Observe a trait once only"

    def _observe_once(change: ChangeType):
        change["owner"].unobserve(_observe_once, names=name)
        try:
            callback(change)
        except Exception as e:
            mb.log.on_error(e, "observe once callback failed", obj)

    obj.observe(_observe_once, name)


def observe_until(
    obj: traitlets.HasTraits, callback: Callable[[ChangeType], None], name: str, predicate: Callable[[Any], bool]
):
    """Observe a trait as it changes until the predicate returns true.

    Intermediate changes are not passed to the callback until the predicated returns true.
    """

    def _observe_until(change: ChangeType):
        if predicate(change["new"]):
            change["owner"].unobserve(_observe_until, names=name)
            try:
                callback(change)
            except Exception as e:
                mb.log.on_error(e, "observe once callback failed", obj)

    obj.observe(_observe_until, name)


async def wait_trait_value(obj: traitlets.HasTraits, name: str, predicate: Callable[[Any], bool]) -> None:
    """Wait until the trait `name` on `obj` returns True from the predicate. The initial value is compared.

    The trait is then observed until the predicate returns `True`.
    """
    event = AsyncEvent()
    if not predicate(getattr(obj, name)):
        mb.utils.observe_until(obj, lambda _: event.set(), name, predicate)
        await event.wait()


def getattr_nested(obj, name: str, default: Any = NO_DEFAULT, *, hastrait_value=True) -> Any:
    """Retrieve a nested attribute from an object.

    This function allows accessing attributes of attributes, specified by a string
    with dot notation.  It also handles the special case of traitlets objects
    with a 'value' trait, automatically returning the value of the trait.
    Args:
        obj: The object from which to retrieve the attribute.
        name: A string representing the attribute to retrieve, possibly with dot
            notation for nested attributes (e.g., 'a.b.c').
        default: If the attribute is not found, return this value. If not provided,
            an AttributeError is raised.
        hastrait_value: If True, and the attribute is a traitlets.HasTraits object
            with a 'value' trait, return the value of the trait. Defaults to True.
    Returns:
        The value of the attribute, or the default value if the attribute is not found
        and a default is provided.
    Raises:
        AttributeError: If the attribute is not found and no default is provided.
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


def iterflatten(iterable: Iterable[T] | Any) -> Generator[T, None, None]:
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


def get_widgets(
    *items: GetWidgetsInputType[S],
    skip_disabled=False,
    skip_hidden=True,
    show=True,
    parent: S | None = None,  # type: ignore
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
                    if parent:
                        try:
                            widget = widget(parent)
                            continue
                        except TypeError:
                            pass
                    widget = widget()
                if isinstance(widget, str):
                    if widget in ["H_FILL", "V_FILL"]:
                        widget = mb.defaults.H_FILL if widget == "H_FILL" else mb.defaults.V_FILL
                        if widget is not last_widget:
                            yield widget
                    else:
                        yield from _get_widgets(getattr_nested(parent, widget, None, hastrait_value=False))
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
                elif isinstance(widget, Iterable):
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
                    app = ipylab.JupyterFrontEnd()
                    app.log.exception(msg, widget, exc_info=e)

    yield from _get_widgets(items)


def hide(widget):
    """Hide the widget."""
    if hasattr(widget, "layout"):
        widget.layout.visibility = "hidden"


def unhide(widget):
    """Unhide the widget."""
    if hasattr(widget, "layout"):
        widget.layout.visibility = "visible"


def set_border(widget, border: str = f"var({CSSvar.menubox_border})"):
    """Set the layout of the widget."""

    if isinstance(widget, mb.Menubox):
        widget.border = border
    else:
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


async def yes_no_dialog(app: ipylab.App, title: str, body: str | ipw.Widget = "", *, names=("Yes", "No")):
    result = await app.dialog.show_dialog(
        title,
        body=body,
        options={
            "buttons": [
                {
                    "ariaLabel": names[0],
                    "label": names[0],
                    "iconClass": "",
                    "iconLabel": "",
                    "caption": names[0],
                    "className": "",
                    "accept": True,
                    "actions": [],
                    "displayType": "default",
                },
                {
                    "ariaLabel": names[1],
                    "label": names[1],
                    "iconClass": "",
                    "iconLabel": "",
                    "caption": names[1],
                    "className": "",
                    "accept": False,
                    "actions": [],
                    "displayType": "warn",
                },
            ],
        },
        has_close=False,
    )
    return result["value"]


def now(*, utc=False):
    "The timestamp for now using this timezone, our utc if specified."
    return pd.Timestamp.now(datetime.UTC if utc else mb.log.TZ)
