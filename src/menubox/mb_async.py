from __future__ import annotations

import enum
import functools
import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, NotRequired, Self, TypedDict, Unpack

import anyio
import wrapt
from async_kernel import Caller
from async_kernel.caller import Future, FutureCancelledError

import menubox as mb
from menubox.utils import funcname

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine, Hashable

    from async_kernel import Future

    from menubox.hasparent import HasParent
    from menubox.trait_types import P, T


__all__ = ["run_async", "run_async_singular", "singular_task", "call_later", "debounce", "periodic", "throttle"]


background_tasks: dict[Future, TaskType] = {}
background_futures: dict[tuple[object, Hashable], Future[Any]] = {}


def _background_future_complete(fut: Future, obj: HasParent | None, handle: Hashable):
    fut_: Future[Any] | None = background_futures.pop((obj, handle), None)
    if fut_ and fut_ is not fut:
        background_futures[(obj, handle)] = fut_
    background_tasks.pop(fut, None)
    try:
        if error := fut.exception():
            if obj:
                obj.on_error(error, "run sync Failed")
            else:
                mb.log.on_error(error, "run sync Failed", obj)
    except FutureCancelledError:
        pass


class TaskType(int, enum.Enum):
    general = enum.auto()
    continuous = enum.auto()
    update = enum.auto()
    init = enum.auto()
    click = enum.auto()


class RunAsyncOptions(TypedDict):
    "Options to use with run_async"

    obj: NotRequired[HasParent | None]
    ""
    handle: NotRequired[str]
    ""
    restart: NotRequired[bool]
    "default: True"
    tasktype: NotRequired[TaskType]
    "default: TaskType.general"
    delay: NotRequired[float]
    ""


def run_async(
    opts: RunAsyncOptions,
    func: Callable[P, Awaitable[T]],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> Future[T]:
    """Run the coroutine function in the main event loop, possibly cancelling a currently
    running future if the name overlaps.

    **Important: A result is returned ONLY when `restart=True`**

    Args:
        func:

    name: The name of the task. If a task with the same name already exists for the object
    it will be cancelled. See run_async_singular as an easier option to prevent accidental
    task cancellation.
    obj:
        `obj` may be a subclass from HasParent
        `obj.handle` if provided adds the task to `obj`. Two options exist:
        1.If the handle is a `set`, `obj` is added to the set
        2 The task is set to obj.<handle>.
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
    handle, obj, restart = opts.get("handle"), opts.get("obj"), opts.get("restart", True)
    if opts:
        if obj and not isinstance(obj, mb.hasparent.HasParent):
            msg = f"{obj} is not an instantance of HasParent."
            raise TypeError(msg)
        # if not obj.has_trait(handle):  # type: ignore
        #     msg = f"{handle=} is not a trait of {limited_string(obj)}!"
        #     raise AttributeError(msg)
        # if not (name := opts.get("name")) and not restart:
        #     msg = "A name must be provided if `restart=False`!"
        #     raise TypeError(msg)
        if (current := get_pending_future(obj=obj, handle=handle)) and not current.done():
            if restart:
                current.cancel()
            else:
                return current
    # else:
    #     current = None

    # async def _run_async_wrapper() -> T:
    #     if current and not current.done():
    #         current.cancel()
    #         with contextlib.suppress(Exception):
    #             await current
    #     try:
    #         result = await func(*args, **kwargs)
    #     except anyio.get_cancelled_exc_class():
    #         raise
    #     except Exception as e:
    #         mb.log.on_error_wrapped(func, obj, str(e), e)
    #         raise
    #     else:
    #         return result

    fut = Caller().get_instance().call_later(func, opts.get("delay", 0), *args, **kwargs)
    if not fut.done():
        background_tasks[fut] = opts.get("tasktype") or TaskType.general
        background_futures[(obj, handle)] = fut
        fut.add_done_callback(functools.partial(_background_future_complete, obj=obj, handle=handle))
        if isinstance(obj, mb.HasParent):
            obj.futures.add(fut)
            fut.add_done_callback(obj.futures.discard)
            if isinstance(handle, str) and obj.has_trait(handle):
                if isinstance(set_ := getattr(obj, handle, None), set):
                    set_.add(fut)
                    fut.add_done_callback(fn=set_.discard)
                else:

                    def on_done(fut):
                        if getattr(obj, handle, None) is fut:
                            obj.set_trait(handle, None)

                    obj.set_trait(handle, fut)

                    fut.add_done_callback(on_done)
    return fut


def run_async_singular(
    opts: RunAsyncOptions, func: Callable[P, Awaitable[T]], /, *args: P.args, **kwargs: P.kwargs
) -> Future[T]:
    if not opts.get("handle"):
        opts["handle"] = f"singular_task_{id(obj) if (obj := opts.get('obj')) else ''}_{funcname(func)}"
    return run_async(opts, func, *args, **kwargs)


def singular_task(**opts: Unpack[RunAsyncOptions]) -> Callable[[Callable[P, T]], Callable[P, Future[T]]]:
    """A decorator to wrap a coroutine function to run as a singular task.

    obj is as the instance.
    kw are passed to run_async_singular such as 'handle'.
    """

    @wrapt.decorator
    def _run_as_singular(wrapped, instance, args, kwargs: dict):
        opts_ = opts | {"obj": instance, "handle": opts.get("handle", wrapped)}
        return run_async(opts_, wrapped, *args, **kwargs)

    return _run_as_singular  # pyright: ignore[reportReturnType]


def get_pending_future(*, obj: HasParent | None = None, handle: str | None = None) -> Future | None:
    """Return the task if it exists.

    If obj is provided, obj tasks will be searched, otherwise the background
    tasks will be searched.
    """
    return background_futures.get((obj, handle)) if (obj or handle) else None


def call_later(delay, callback, *args, **kwargs) -> None:
    """Run callback after a delay."""
    # TODO: remove
    Caller.get_instance().call_later(callback, delay, *args, **kwargs)


async def to_thread(func: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs) -> T:
    """Run a function in an executor."""
    # TODO: remove
    return await Caller.to_thread(func, *args, **kwargs)


class PeriodicMode(enum.StrEnum):
    debounce = "debounce"
    throttle = "throttle"
    periodic = "periodic"


class _Periodic:
    __slots__ = ("_repeat", "fut", "wrapped", "instance", "args", "kwargs", "wait", "mode")

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

    async def _periodic_async(self):
        try:
            while self._repeat:
                self._repeat = False
                if self.mode is PeriodicMode.debounce:
                    await anyio.sleep(self.wait)
                if getattr(self.instance, "closed", False):
                    msg = f"{self.instance} is closed!"
                    raise anyio.get_cancelled_exc_class()(msg)  # noqa: TRY301
                result = self.wrapped(*self.args, **self.kwargs)
                while inspect.isawaitable(result):
                    result = await result
                await anyio.sleep(0 if self.mode is PeriodicMode.debounce else self.wait)
        except anyio.get_cancelled_exc_class():
            if getattr(self.instance, "closed", False):
                return
            raise
        except Exception as e:
            mb.log.on_error_wrapped(self.wrapped, self.instance, f"{e} <period mode={self.mode}>", e)
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
    _periodic_tasks: dict[tuple[object | None, Callable], _Periodic] = {}

    def on_done(k, task):
        info = _periodic_tasks.get(k)
        if info and info.fut is task:
            info.fut = info.wrapped = info.instance = None
            del _periodic_tasks[k]

    @wrapt.decorator
    def _periodic_wrapper(wrapped, instance, args, kwargs):
        k = (instance, wrapped)
        info = _periodic_tasks.get(k)
        if info and info._repeat is not None:
            info._repeat = True
            info.args = args
            info.kwargs = kwargs
            return info.fut
        info = _Periodic(wrapped, instance, args, kwargs, wait, mode)
        info.fut = run_async(RunAsyncOptions(handle=wrapped, obj=instance, tasktype=tasktype), info, **kw)
        _periodic_tasks[k] = info
        info.fut.add_done_callback(functools.partial(on_done, k))
        return info.fut

    return _periodic_wrapper


def throttle(wait: float, tasktype=TaskType.general, **kw) -> Callable[..., Callable[..., Future]]:
    """A decorator that throttles the call to wrapped function.

    Compatible with coroutines, functions and methods.

    Returns a task.
    """
    return periodic(wait, mode=PeriodicMode.throttle, tasktype=tasktype, **kw)  # type: ignore


def debounce(wait: float, tasktype=TaskType.general, **kw) -> Callable[..., Callable[..., Future]]:
    """A decorator that debounces the call to the wrapped function.

    Compatible with coroutines, functions and methods.

    Returns a task.
    """
    return periodic(wait, mode=PeriodicMode.debounce, tasktype=tasktype, **kw)  # type: ignore
