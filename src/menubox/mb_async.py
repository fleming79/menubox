from __future__ import annotations

import asyncio
import enum
import functools
import inspect
import weakref
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, ParamSpec, TypeVar, cast

import wrapt

import menubox as mb
from menubox.utils import funcname, limited_string

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from menubox.hasparent import HasParent


T = TypeVar("T")
R = TypeVar("R")
P = ParamSpec("P")


__all__ = ["run_async", "run_async_singular", "singular_task", "call_later", "debounce", "periodic", "throttle"]


background_tasks: weakref.WeakKeyDictionary[asyncio.Task, TaskType] = weakref.WeakKeyDictionary()
_background_tasks = set[asyncio.Task]()  # A strong ref for task that down belong to an object.


def _background_task_complete(task: asyncio.Task):
    background_tasks.pop(task, None)
    _background_tasks.discard(task)


class TaskType(int, enum.Enum):
    general = enum.auto()
    continuous = enum.auto()
    update = enum.auto()
    init = enum.auto()
    click = enum.auto()


def run_async(
    aw: Awaitable[T] | Callable[[], Awaitable[T]],
    *,
    name: str | None = None,
    obj: HasParent | None = None,
    handle: str = "",
    restart=True,
    timeout: float | None = None,
    tasktype=TaskType.general,
):
    """Run aw as a task, possibly cancelling an existing task if the name overlaps.

    Also accepts a callables that return produces an awaitable.

    A strong ref is kept for the task in either obj.tasks

    **Important: A result is returned ONLY when `restart=True`**

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
        msg = "A name must be provided if `restart=False`!"
        raise TypeError(msg)
    current = _get_task(name) if name else None
    if current:
        if not restart and not current.cancelling() and not current.done():
            return current
        current.cancel(f"Restarting task {name=}")

    async def _run_async_wrapper(aw_=aw):
        if current and not current.done():
            await asyncio.wait([current])
        try:
            if callable(aw_):
                aw_ = aw_()
            if timeout:
                async with asyncio.timeout(timeout):
                    result = await aw_
            result = await aw_
        except Exception as e:
            mb.log.on_error(aw_, obj, "run async", e)
            raise
        else:
            return result if restart else None

    task = asyncio.create_task(_run_async_wrapper(), name=name)
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
                    if getattr(obj, handle, None) is task:
                        obj.set_trait(handle, None)

                obj.set_trait(handle, task)

                task.add_done_callback(on_done)
    else:
        _background_tasks.add(task)
    return task


def run_async_singular(
    aw: Awaitable[T] | functools.partial[T], *, obj: HasParent | None = None, name: str | None = None, **kwargs
) -> asyncio.Task[T]:
    """Schedule the aw for execution with run_async.

    A singular task `name` is either:
    1. name
    2. f"singular_task_{ID}_{funcname(aw)}"

    **kwargs are passed to `run_async`.
    """
    return run_async(
        aw,  # type: ignore
        name=name or f"singular_task_{id(obj) if obj else ''}_{funcname(aw)}",
        obj=obj if isinstance(obj, mb.HasParent) else None,
        **kwargs,
    )  # type: ignore


def singular_task(restart=True, **kw) -> Callable[..., Callable[..., asyncio.Task]]:
    """A decorator to wrap a coroutine function to run as a singular task.

    obj is as the instance.
    kw are passed to run_async_singular such as 'handle'.
    """

    @wrapt.decorator
    def _run_as_singular(wrapped: Awaitable[T], instance, args, kwargs: dict):
        if not inspect.iscoroutinefunction(wrapped):
            msg = "The wrapped function must be coroutine function."
            raise TypeError(msg)
        # use partial to avoid creating coroutines that may never be awaited
        restart_ = restart
        if "restart" in kwargs:
            restart_ = kwargs.pop("restart")
        func = functools.partial(wrapped, *args, **kwargs)
        return run_async_singular(cast(Awaitable[T], func), **{"obj": instance, "restart": restart_} | kw)

    return _run_as_singular  # type: ignore


def _get_task(name: str):
    """Return the task if it exists."""
    for task in background_tasks:
        if task.get_name() == name:
            return task
    return None


def call_later(delay, callback, *args, **kwargs):
    """Run callback after a delay."""
    callit = functools.partial(callback, *args, **kwargs)
    asyncio.get_running_loop().call_later(delay, callit)


async def to_thread(func: Callable[P, T], *args: P.args, **kwargs: P.kwargs):
    """Run a function in an executor.

    This uses asyncio.to_thread, but catches exceptions re-raising them
    inside the calling
    """

    def func_call():
        try:
            result = func(*args, **kwargs)
        except Exception as e:
            return {"exception": e}
        else:
            return {"result": result}

    result = await asyncio.to_thread(func_call)
    try:
        return cast(T, result["result"])
    except KeyError:
        pass
    e: Exception = result["exception"]  # type: ignore
    e.add_note(f'This exception occurred while executing "{funcname(func)}" inside "mb_async.to_thread".')
    raise e


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
                if getattr(self.instance, "closed", False):
                    asyncio.current_task().cancel(f"{self.instance} is closed!")  # type: ignore
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
