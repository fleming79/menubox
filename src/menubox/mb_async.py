from __future__ import annotations

import enum
import functools
import inspect
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, NotRequired, Self, TypedDict, Unpack

import anyio
import wrapt
from async_kernel import Caller
from async_kernel.pending import Pending, PendingCancelled, PendingManager, PendingTracker
from ipylab import JupyterFrontEnd

import menubox as mb

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Hashable
    from types import CoroutineType

    from async_kernel import Pending

    from menubox.hasparent import HasParent
    from menubox.trait_types import P, T


__all__ = ["PenType", "debounce", "periodic", "run_async", "singular", "throttle"]


singular_pending: dict[Hashable, Pending[Any]] = {}


class PenType(int, enum.Enum):
    general = enum.auto()
    continuous = enum.auto()
    update = enum.auto()
    init = enum.auto()
    click = enum.auto()
    debounce = enum.auto()
    throttle = enum.auto()
    update_children = enum.auto()
    "Children are being updated"


MANAGER_ONLY = [PenType.continuous, PenType.throttle, PenType.debounce, PenType.update_children]
"A list of PenTypes which should be omitted from PendingGroup trackers."


def get_trackers(pentype: PenType | None, /) -> type[PendingManager | PendingTracker]:
    if pentype in MANAGER_ONLY:
        return PendingManager
    return PendingTracker


class RunAsyncOptions(TypedDict):
    "Options to use with run_async"

    key: NotRequired[Hashable]
    "Specify a key to use with 'singular_instances'"
    restart: NotRequired[bool]
    """
    Whether to restart a pending with a matching `key` default: `True`.

    If `False` the current call arguments are ignored and the current pending (`Pending`) is returned.
    """
    obj: NotRequired[HasParent | None]
    ""
    handle: NotRequired[str]
    """
    The name of the trait on `obj` where to store the pending.

    Both Pending instance and set traits are permitted.
    """
    pentype: NotRequired[PenType]
    "default: PenType.general."

    delay: NotRequired[float]
    "A delay in seconds to wait before executing `func`."

    ignore_error: NotRequired[bool]
    "Set to True to avoid the exception being passed to obj.on_error or logged."


def _on_done_callback(pen: Pending):
    if (key := pen.metadata.get("key")) and singular_pending.get(key) is pen:
        singular_pending.pop(key)
    if obj := get_obj_using_metadata(pen.metadata):
        obj.pending.discard(pen)
        if handle := pen.metadata.get("handle"):
            if isinstance(set_ := getattr(obj, handle), set):
                set_.discard(pen)
            elif getattr(obj, handle) is pen:
                obj.set_trait(handle, None)
    if (not pen.cancelled()) and (error := pen.exception()) and (not pen.metadata.get("ignore_error")):
        if obj:
            if not obj.closed:
                obj.on_error(error, msg="run async failed")
        elif not isinstance(error, PendingCancelled):
            mb.log.on_error(error, msg="run async failed")
    elif obj and obj.log.getEffectiveLevel() == 10:
        obj.log.debug(f"Pending complete: {pen}")


def get_obj_using_metadata(metadata: RunAsyncOptions | dict) -> HasParent[Any] | None:
    "Get the most relevant from the metadata  by looking in various places"
    obj = metadata.get("obj")
    if isinstance(obj, mb.HasParent):
        return obj
    if (func := metadata.get("func")) and isinstance(obj := getattr(func, "__self__", None), mb.HasParent):
        return obj
    return None


def run_async(
    opts: RunAsyncOptions,
    func: Callable[P, T | CoroutineType[Any, Any, T]],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> Pending[T]:
    """
    Run function in the main event loop, possibly cancelling a currently
    running Pending if the name overlaps.

    **Important: A result is returned ONLY when `restart=True`**

    Args:
        opts: Options to control how it is called and information to associate with the pending as metadata.
        func: The function to call.
        args: positional arguments.
        kwargs: keyword arguments.
    """

    if (key := opts.get("key")) and (current := singular_pending.pop(key, None)) and not current.done():
        if opts.get("restart", True):
            current.cancel()
        else:
            singular_pending[key] = current
            return current

    pen = Caller("MainThread").schedule_call(
        func,
        args,
        kwargs,
        None,
        get_trackers(opts.get("pentype")),
        delay=opts.get("delay", 0),
        start_time=time.monotonic(),
    )
    pen.add_done_callback(_on_done_callback)
    pen.metadata.update(opts)
    if key:
        singular_pending[key] = pen
    if obj := get_obj_using_metadata(pen.metadata):
        if obj.closed:
            pen.cancel(f"{obj=} is closed!")
        obj.pending.add(pen)
        if handle := pen.metadata.get("handle"):
            if isinstance(set_ := getattr(obj, handle), set):
                set_.add(pen)
            else:
                obj.set_trait(handle, pen)
    obj = obj or JupyterFrontEnd()
    if obj.log.getEffectiveLevel() == 10:
        obj.log.debug(f"Pending started: {pen}")
    return pen


def singular(
    **opts: Unpack[RunAsyncOptions],
) -> Callable[[Callable[P, CoroutineType[Any, Any, T]]], Callable[P, Pending[T]]]:
    """
    A decorator to wrap a coroutine function to run as a singular pending.

    obj is as the instance.
    kw are passed to run_async_singular such as 'handle'.
    """

    @wrapt.decorator
    def _run_as_singular(wrapped, instance, args, kwargs: dict):
        opts_ = opts | {"key": wrapped, "obj": instance or wrapped}
        return run_async(opts_, wrapped, *args, **kwargs)

    return _run_as_singular  # pyright: ignore[reportReturnType]


def to_thread(
    func: Callable[P, T | CoroutineType[Any, Any, T]],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> Pending[T]:
    """Run a function in a separate thread."""
    return Caller("MainThread").to_thread(func, *args, **kwargs)


class PeriodicMode(enum.StrEnum):
    debounce = "debounce"
    throttle = "throttle"
    periodic = "periodic"


class _Periodic:
    __slots__ = (
        "_repeat",
        "args",
        "instance",
        "kwargs",
        "mode",
        "pen",
        "wait",
        "wrapped",
    )

    def __repr__(self) -> str:
        return f"<Period {self.mode} {self.wrapped!r}"

    def __new__(cls, wrapped, instance, args, kwargs, wait, mode) -> Self:
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

    async def _periodic_async(self) -> None:
        while self._repeat:
            self._repeat = False
            if self.mode is PeriodicMode.debounce:
                await anyio.sleep(self.wait)
            if getattr(self.instance, "closed", False):
                break
            result = self.wrapped(*self.args, **self.kwargs)
            if inspect.iscoroutine(result):
                result = await result
            await anyio.sleep(0 if self.mode is PeriodicMode.debounce else self.wait)


def periodic(
    wait, mode: PeriodicMode = PeriodicMode.periodic, pentype=PenType.continuous
) -> Callable[[Callable[P, T | CoroutineType[Any, Any, T]]], Callable[P, Pending[T]]]:
    """
    A wrapper to control the rate at which a function may be called.

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
    Returns the current pending.
    """

    mode = PeriodicMode(mode)
    pentype = PenType(pentype)
    _pending: dict[tuple[object | None, Callable], _Periodic] = {}

    def on_done(k, pending):
        info = _pending.get(k)
        if info and info.pen is pending:
            info.pen = info.wrapped = info.instance = None
            del _pending[k]

    @wrapt.decorator
    def _periodic_wrapper(wrapped, instance, args, kwargs):
        k = (instance, wrapped)
        info = _pending.get(k)
        if info and info._repeat is not None:
            info._repeat = True
            info.args = args
            info.kwargs = kwargs
            return info.pen
        info = _Periodic(wrapped, instance, args, kwargs, wait, mode)
        info.pen = run_async(RunAsyncOptions(key=wrapped, obj=instance, pentype=pentype), info)
        _pending[k] = info
        info.pen.add_done_callback(functools.partial(on_done, k))
        return info.pen

    return _periodic_wrapper  # pyright: ignore[reportReturnType]


def throttle(
    wait: float, pentype=PenType.throttle
) -> Callable[[Callable[P, T | CoroutineType[Any, Any, T]]], Callable[P, Pending[T]]]:
    """
    A decorator that throttles the call to wrapped function.

    Compatible with coroutines, functions and methods.

    Returns a [async_kernel.caller.Pending][].
    """
    return periodic(wait, mode=PeriodicMode.throttle, pentype=pentype)


def debounce(
    wait: float, pentype=PenType.debounce
) -> Callable[[Callable[P, T | CoroutineType[Any, Any, T]]], Callable[P, Pending[T]]]:
    """
    A decorator that debounces the call to the wrapped function.

    Compatible with coroutines, functions and methods.

    Returns a [async_kernel.caller.Pending][].
    """
    return periodic(wait, mode=PeriodicMode.debounce, pentype=pentype)
