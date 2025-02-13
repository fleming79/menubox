from __future__ import annotations

import asyncio
import enum
import functools
import inspect
import weakref
from collections.abc import Awaitable, Callable, Iterable
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast

import ipylab
import ipylab.log
import ipywidgets as ipw
import pandas as pd
import toolz
import traitlets
import wrapt

import menubox as mb
from menubox.defaults import NO_DEFAULT

if TYPE_CHECKING:
    from collections.abc import Coroutine, Generator

    from menubox.hasparent import HasParent
    from menubox.trait_types import ChangeType


AW = TypeVar("AW")
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
    "debounce",
    "limited_string",
    "tuple_discard",
    "tuple_add",
    "run_async",
    "run_async_singular",
    "singular_task",
    "cancel_task",
    "get_task",
    "call_later",
    "wait_for",
    "funcname",
    "sanatise_name",
    "sanatise_filename",
    "iterflatten",
    "weak_observe",
]


background_tasks: dict[asyncio.Task, TaskType] = {}


def _background_task_complete(task: asyncio.Task):
    background_tasks.pop(task, None)


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



class TaskType(int, enum.Enum):
    general = enum.auto()
    continuous = enum.auto()
    update = enum.auto()
    init = enum.auto()
    click = enum.auto()


def run_async(
    aw: Awaitable[AW] | functools.partial,
    *,
    name: str | None = None,
    obj: HasParent | None = None,
    handle: str = "",
    restart=True,
    timeout: float | None = None,
    tasktype=TaskType.general,
) -> asyncio.Task[AW]:
    """Run aw as a task, possibly cancelling an existing task if the name overlaps.

    Also accepts a partial function provided that it produces an awaitable.

    Parameters
    ----------

    name: The name of the task. If a task with the same name already exists it will
    be cancelled. See run_async_singular as an easier option to prevent accidental
    task cancellation.
    obj:
        `obj` may be a subclass from HasParent
        `obj.handle` if provided adds the task to `obj`. Two options exist:
        1.If the handle is a `set`, `obj` is added to the set
        2 The task is set to obj.<handle>.
    timeout:
        The timeout for the task to complete. A Timeout exception will be raised.
    widget:
        A widget is disabled for the duration of the task.
    loginfo:
        Provided to aid with the exception details.
    On completion the task is removed from the set or replaced with `None`.
    :
        Make identifiable as an update task as used by HasParent.wait_update_tasks()

    Exceptions for cancelled tasks are not raised.
    widget: If provided the widget is disabled immediately and then disabled once the
        awaitable is completed.
    """

    if handle:
        if obj and not isinstance(obj, mb.hasparent.HasParent):
            msg = f"{obj} is not an instantance of HasParent."
            raise TypeError(msg)
        if not obj.has_trait(handle):  # type: ignore
            msg = f"{handle=} is not a trait of {limited_string(obj)}!"
            raise AttributeError(msg)
    if not restart and not name:
        msg = "A name must be provided if restart=False!"
        raise TypeError(msg)
    current = get_task(name)
    if current:
        if not restart and not current.cancelling() and not current.done():
            return current
        current.cancel()

    async def _run_async_wrapper():
        if current and not current.done():
            await asyncio.wait([current])
        aw_ = None
        try:
            aw_ = aw() if callable(aw) else aw
            if timeout:
                async with asyncio.timeout(timeout):
                    return await aw_
            return await aw_
        except Exception as e:
            mb.log.on_error(aw_ or aw, obj, "run async", e)
            raise

    loop = asyncio.get_running_loop()
    task = loop.create_task(_run_async_wrapper(), name=name)
    background_tasks[task] = tasktype
    task.add_done_callback(_background_task_complete)
    if isinstance(obj, mb.HasParent):
        obj.tasks.add(task)
        task.add_done_callback(obj.tasks.discard)
        if handle:
            if isinstance(set_ := getattr(obj, handle, None), set):
                set_.add(task)
                task.add_done_callback(set_.discard)
            else:

                def on_done(task):
                    if getattr(obj, handle, None) is task and isinstance(obj, mb.HasParent):
                        obj.set_trait(handle, None)

                obj.set_trait(handle, task)

                task.add_done_callback(on_done)
    return task


def run_async_singular(
    aw: Awaitable[AW] | functools.partial[AW], *, obj: HasParent | None = None, name: str | None = None, **kwargs
) -> asyncio.Task[AW]:
    """Schedule the aw for execution with run_async.

    A singular task `name` is either:
    1. name
    2. f"singular_task_{ID}_{funcname(aw)}"

    **kwargs are passed to `run_async`.
    """
    return run_async(
        aw,
        name=name or f"singular_task_{id(obj) if obj else ''}_{funcname(aw)}",
        obj=obj if isinstance(obj, mb.HasParent) else None,
        **kwargs,
    )


def singular_task(*, restart=True, **kw) -> Callable[..., Callable[..., asyncio.Task]]:
    """A decorator to wrap a coroutine function to run as a singular task.

    obj is as the instance.
    kw are passed to run_async_singular such as 'handle'.
    """

    @wrapt.decorator
    def _run_as_singular(wrapped: Awaitable[AW], instance, args, kwargs: dict) -> asyncio.Task[AW]:
        if not inspect.iscoroutinefunction(wrapped):
            msg = "The wrapped function must be coroutine function."
            raise TypeError(msg)
        # use partial to avoid creating coroutines that may never be awaited
        restart_ = restart
        if "restart" in kwargs:
            restart_ = kwargs.pop("restart")
        func = functools.partial(wrapped, *args, **kwargs)
        return run_async_singular(cast(Awaitable[AW], func), **{"obj": instance, "restart": restart_} | kw)

    return _run_as_singular  # type: ignore


def cancel_task(task):
    """Cancel the first found task with name from background tasks."""

    if not task:
        return
    if isinstance(task, str):
        for task_ in background_tasks:
            if task_.get_name() == task:
                if not task_.done():
                    task_.cancel()
                return
    elif isinstance(task, asyncio.Task):
        if hasattr(task, "done") and not task.done():
            task.cancel()
    else:
        msg = f"{type(task)}"
        raise NotImplementedError(msg)


def get_task(task: str | asyncio.Task | None):
    """Return the task if it exists."""
    if task is None:
        return None
    if isinstance(task, asyncio.Task):
        return task
    if not isinstance(task, str):
        msg = f"{type(task)}"
        raise TypeError(msg)
    for task_ in background_tasks:
        if task_.get_name() == task:
            return task_
    return None


def call_later(delay, callback, *args, **kwargs):
    """Run callback after a delay."""
    callit = functools.partial(callback, *args, **kwargs)
    asyncio.get_running_loop().call_later(delay, callit)


async def wait_for(fut, timeout: float | None = None, info=""):
    """If coro is awaitable, wait for and return the result.

    fut name and info are used in a timeout message.
    """
    if asyncio.isfuture(fut) or asyncio.iscoroutine(fut):
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except TimeoutError:
            info = f" {info=}." if info else "."
            msg = f"Timeout after {timeout=}s waiting for {funcname(fut)}(){info}"
            raise TimeoutError(msg) from None
    return fut


## Periodic functions initially inspired by:
# https://github.com/jupyter-widgets/ipywidgets/blob/d35010f2e5abd7ae306902e177529be5eb42c441/docs/source/examples/Widget%20Events.ipynb
## They are now usable in all expected contexts as per https://wrapt.readthedocs.io/en/latest/decorators.html#universal-decorators


def _is_discontinued(obj):
    # Need to handle class methods that will test positive always with a simple test.
    return getattr(obj, "discontinued", False) is True


class PeriodicMode(str, enum.Enum):
    debounce = "debounce"
    throttle = "throttle"
    periodic = "periodic"


class _Periodic:
    __slots__ = ("_repeat", "task", "wrapped", "instance", "args", "kwargs", "wait", "mode")

    def __new__(cls, wrapped, instance, args, kwargs, wait, mode):
        self = super().__new__(cls)
        self._repeat = True
        self.wrapped = wrapped
        self.instance = instance
        self.args = args
        self.kwargs = kwargs
        self.wait = wait
        self.mode = mode
        return self

    def __call__(self) -> Coroutine:
        return self._periodic_async()

    async def _periodic_async(self):
        try:
            while self._repeat:
                self._repeat = False
                if self.mode is PeriodicMode.debounce:
                    await asyncio.sleep(self.wait)
                elif self._repeat:
                    continue
                if _is_discontinued(self.instance):
                    raise asyncio.CancelledError  # noqa: TRY301
                result = self.wrapped(*self.args, **self.kwargs)
                while inspect.isawaitable(result):
                    result = await result
                if self.mode is PeriodicMode.debounce:
                    await asyncio.sleep(0)
                else:
                    await asyncio.sleep(self.wait)
        except asyncio.CancelledError:
            return
        except Exception as e:
            mb.log.on_error(self.wrapped, self.instance, self.mode, e)
            raise



def periodic(wait, mode: PeriodicMode = PeriodicMode.periodic, tasktype=TaskType.continuous, **kw):
    """A wrapper to control the rate at which a function may be called.

    Can wrap functions, coroutines and methods. Several modes are supported.
    Parameters
    ----------
    mode:
        "debounce":
            Sleep for wait until the last call is received before running the function.
        "throttle":
            Call once every debounce period whilst being called. Will
            Always run until after the last call is made.
        "periodic":
            Run periodically forever.
    kw are passed to run_async_singular
    Returns the current task.
    """

    mode = PeriodicMode(mode)
    tasktype = TaskType(tasktype)
    _periodic_tasks: dict[tuple[Callable, object | None], _Periodic] = {}

    def on_done(k, task):
        info = _periodic_tasks.get(k)
        if info and info.task is task:
            info.task = info.wrapped = info.instance = None
            del _periodic_tasks[k]

    @wrapt.decorator
    def _periodic_wrapper(wrapped, instance, args, kwargs):
        if _is_discontinued(instance):
            return None
        k = (instance, wrapped)
        info = _periodic_tasks.get(k)
        if info and info._repeat is not None:
            info._repeat = True
            info.args = args
            info.kwargs = kwargs
            return info.task
        info = _Periodic(wrapped, instance, args, kwargs, wait, mode)
        info.task = run_async(
            info,  # type: ignore
            name=f"{tasktype.name} {funcname(wrapped)} {id(instance or wrapped)}",
            obj=instance if isinstance(instance, mb.HasParent) else None,
            tasktype=tasktype,
            **kw,
        )
        _periodic_tasks[k] = info
        info.task.add_done_callback(functools.partial(on_done, k))
        return info.task

    return _periodic_wrapper


def throttle(wait: float, tasktype=TaskType.general, **kw) -> Callable[..., Callable[..., asyncio.Task]]:
    """A decorator that throttles the call to wrapped function.

    Compatible with coroutines and functions and methods.

    pass log=defaults.NO_VALUE to disable all logging.

    Returns a task.
    """
    return periodic(wait, mode=PeriodicMode.throttle, tasktype=tasktype, **kw)  # type: ignore


def debounce(wait: float, tasktype=TaskType.general, **kw) -> Callable[..., Callable[..., asyncio.Task]]:
    """A decorator that debounces the call to the wrapped function.

    Compatible with coroutines and functions and methods.
    Returns a task.
    """
    return periodic(wait, mode=PeriodicMode.debounce, tasktype=tasktype, **kw)  # type: ignore


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
    """Set a nested attribute using dotted notation in the name.

    default_setter: callable
        set the attribute. If the object doesn't have its own setter
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


def fullname(obj) -> str:
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
            return f"{obj.__module__}.{obj.__name__}"
        module = obj.__class__.__module__
        if module is None or module == str.__class__.__module__:
            return obj.__class__.__name__
    except Exception:
        return str(obj)
    else:
        return f"{module}.{obj.__class__.__name__}"


def funcname(obj: Any) -> str:
    """Get function name for a callable or task.

    Known to work for standard functions, methods and functools.partial
    """
    if hasattr(obj, "__wrapped__"):
        return funcname(obj.__wrapped__)
    if isinstance(obj, _Periodic):
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
    """Eval template with the mapped globals.

    template must not contain triple quote '''
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
    """
    replace: str
        replace each invalid symbol
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


def close_obj(obj: ipw.Widget | HasParent | Any) -> None:
    """Close widgets and discontinue Hasparent and clear children from ipywidget box."""
    if hasattr(obj, "close"):
        obj.close()


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


def get_widgets(
    *items,
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
    if isinstance(obj, mb.MenuBox) and obj.discontinued:
        msg = f"The instance of {fullname(obj)} is discontinued!"
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
