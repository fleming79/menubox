from __future__ import annotations

import enum
import functools
import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, NotRequired, Self, TypedDict, Unpack

import anyio
import wrapt
from async_kernel import Caller
from async_kernel.caller import Future
from ipylab import App

import menubox as mb

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Hashable
    from types import CoroutineType

    from async_kernel import Future

    from menubox.hasparent import HasParent
    from menubox.trait_types import P, T


__all__ = ["run_async", "singular_task", "debounce", "periodic", "throttle"]


singular_tasks: dict[Hashable, Future[Any]] = {}


class TaskType(int, enum.Enum):
    general = enum.auto()
    continuous = enum.auto()
    update = enum.auto()
    init = enum.auto()
    click = enum.auto()


class RunAsyncOptions(TypedDict):
    "Options to use with run_async"

    key: NotRequired[Hashable]
    "Specify a key to use with 'singular_instances'"
    restart: NotRequired[bool]
    """
    Whether to restart a task with a matching `key` default: `True`.

    If `False` the current call arguments are ignored and the current task (`Future`) is returned.
    """
    obj: NotRequired[HasParent | None]
    ""
    handle: NotRequired[str]
    """
    The name of the trait on `obj` where to store the future of the task.

    Both Future instance and set traits are permitted.
    """
    tasktype: NotRequired[TaskType]
    "default: TaskType.general."
    delay: NotRequired[float]
    "A delay in seconds to wait before executing `func`."
    concurrency_mode: NotRequired[Literal["task", "thread"]]
    "default is 'task'."
    thread_name: NotRequired[str | None]
    "The thread name to use when concurrency mode is 'thread'."


def _on_done_callback(fut: Future):
    if (key := fut.metadata.get("key")) and singular_tasks[key] is fut:
        singular_tasks.pop(key)
    if obj := get_obj_using_metadata(fut.metadata):
        obj.tasks.discard(fut)
        if handle := fut.metadata.get("handle"):
            if isinstance(set_ := getattr(obj, handle), set):
                set_.discard(fut)
            elif getattr(obj, handle) is fut:
                obj.set_trait(handle, None)
    if not fut.cancelled() and (error := fut.exception()):
        if obj:
            obj.on_error(error, msg="run sync Failed")
        else:
            mb.log.on_error(error, "run sync Failed")

    obj = obj or App()
    if obj.log.getEffectiveLevel() == 10:
        obj.log.debug(f"Task complete: {fut}")


def get_obj_using_metadata(metadata: RunAsyncOptions | dict) -> HasParent[Any] | None:
    "Get the most relevant from the metadata  by looking in various places"
    obj = metadata.get("obj")
    if isinstance(obj, mb.HasParent):
        return obj
    if (func := metadata.get("func")) and isinstance(obj := getattr(func, "__self__", None), mb.HasParent):
        return obj
    return None


def run_async(
    opts: RunAsyncOptions, func: Callable[P, T | CoroutineType[Any, Any, T]], /, *args: P.args, **kwargs: P.kwargs
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

    if (key := opts.get("key")) and (current := singular_tasks.pop(key, None)) and not current.done():
        if opts.get("restart", True):
            current.cancel()
        else:
            singular_tasks[key] = current
            return current
    match opts.get("concurrency_mode", "task"):
        case "task":
            caller = Caller.get_instance()
            fut = caller.call_later(opts.get("delay", 0), func, *args, **kwargs)
        case "thread":
            fut = Caller.to_thread_by_name(opts.get("thread_name"), func, *args, **kwargs)
    fut.add_done_callback(_on_done_callback)
    fut.metadata.update(opts)
    if key:
        singular_tasks[key] = fut
    if obj := get_obj_using_metadata(fut.metadata):
        obj.tasks.add(fut)
        if handle := fut.metadata.get("handle"):
            if isinstance(set_ := getattr(obj, handle), set):
                set_.add(fut)
            else:
                obj.set_trait(handle, fut)
    obj = obj or App()
    if obj.log.getEffectiveLevel() == 10:
        obj.log.debug(f"Task started: {fut}")
    return fut


def singular_task(
    **opts: Unpack[RunAsyncOptions],
) -> Callable[[Callable[P, CoroutineType[Any, Any, T]]], Callable[P, Future[T]]]:
    """A decorator to wrap a coroutine function to run as a singular task.

    obj is as the instance.
    kw are passed to run_async_singular such as 'handle'.
    """

    @wrapt.decorator
    def _run_as_singular(wrapped, instance, args, kwargs: dict):
        opts_ = opts | {"key": wrapped, "obj": instance or wrapped}
        return run_async(opts_, wrapped, *args, **kwargs)

    return _run_as_singular  # pyright: ignore[reportReturnType]


def to_thread(func: Callable[P, T | CoroutineType[Any, Any, T]], /, *args: P.args, **kwargs: P.kwargs) -> Future[T]:
    """Run a function in a separate thread."""
    return run_async({"concurrency_mode": "thread"}, func, *args, **kwargs)


class PeriodicMode(enum.StrEnum):
    debounce = "debounce"
    throttle = "throttle"
    periodic = "periodic"


class _Periodic:
    __slots__ = ("_repeat", "task", "wrapped", "instance", "args", "kwargs", "wait", "mode")

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
            while inspect.isawaitable(result):
                result = await result
            await anyio.sleep(0 if self.mode is PeriodicMode.debounce else self.wait)


def periodic(
    wait, mode: PeriodicMode = PeriodicMode.periodic, tasktype=TaskType.continuous
) -> Callable[[Callable[P, T | CoroutineType[Any, Any, T]]], Callable[P, Future[T]]]:
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
        if info and info.task is task:
            info.task = info.wrapped = info.instance = None
            del _periodic_tasks[k]

    @wrapt.decorator
    def _periodic_wrapper(wrapped, instance, args, kwargs):
        k = (instance, wrapped)
        info = _periodic_tasks.get(k)
        if info and info._repeat is not None:
            info._repeat = True
            info.args = args
            info.kwargs = kwargs
            return info.task
        info = _Periodic(wrapped, instance, args, kwargs, wait, mode)
        info.task = run_async(RunAsyncOptions(key=wrapped, obj=instance, tasktype=tasktype), info)
        _periodic_tasks[k] = info
        info.task.add_done_callback(functools.partial(on_done, k))
        return info.task

    return _periodic_wrapper  # pyright: ignore[reportReturnType]


def throttle(
    wait: float, tasktype=TaskType.general
) -> Callable[[Callable[P, T | CoroutineType[Any, Any, T]]], Callable[P, Future[T]]]:
    """A decorator that throttles the call to wrapped function.

    Compatible with coroutines, functions and methods.

    Returns a [async_kernel.caller.Future][].
    """
    return periodic(wait, mode=PeriodicMode.throttle, tasktype=tasktype)


def debounce(
    wait: float, tasktype=TaskType.general
) -> Callable[[Callable[P, T | CoroutineType[Any, Any, T]]], Callable[P, Future[T]]]:
    """A decorator that debounces the call to the wrapped function.

    Compatible with coroutines, functions and methods.

    Returns a [async_kernel.caller.Future][].
    """
    return periodic(wait, mode=PeriodicMode.debounce, tasktype=tasktype)
