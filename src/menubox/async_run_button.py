from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Generic, Literal

import ipywidgets as ipw
import traitlets

from menubox import hasparent, mb_async, utils
from menubox import trait_factory as tf
from menubox.css import CSScls
from menubox.hasparent import HasParent, Parent
from menubox.log import log_exceptions
from menubox.trait_types import S

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from types import CoroutineType


class AsyncRunButton(HasParent, ipw.Button, Generic[S]):
    """A button that runs the function in a singular task that can be cancelled by
    clicking the button again.

    Additional methods are added to the button `start`, `cancel`, `cancel_wait` which
    control the button action. The active task is added as the attribute `task`.

    parent: HasParent | None
        Parent is passed as obj to run_async_singular.
    c_func: async | AsyncRunButton | str
        This is the function or AsyncRunButton to call with kw. Noting that the tasks
        are linked, so cancelling one will cancel the other. Strings are also accepted
        with dotted name access relative to parent.
    link_button:
        Disable the button while the other button is running (if not called )
    kw : dict | callable
    If kw is callable, it will be called when the button is clicked.  It must return a
    dict.
    """

    parent: Parent[S] = Parent(HasParent)  # type: ignore
    _update_disabled = False
    description = traitlets.Unicode(read_only=True).tag(sync=True)
    task = tf.Task()

    def __new__(cls, cfunc: Callable[[S], Callable[..., CoroutineType] | AsyncRunButton], parent: S, **kwargs):
        return super().__new__(cls, parent=parent, cfunc=cfunc, **kwargs)

    def __init__(
        self,
        cfunc: Callable[[S], Callable[..., CoroutineType] | AsyncRunButton],
        *,
        parent: S,
        description="Start",
        cancel_description="Cancel",
        kw: Callable[[S], dict] | None = None,
        style: dict | None = None,
        button_style: Literal["primary", "success", "info", "warning", "danger", ""] = "primary",
        cancel_button_style: Literal["primary", "success", "info", "warning", "danger", ""] = "warning",
        tooltip="",
        link_button=False,
        tasktype: mb_async.TaskType = mb_async.TaskType.general,
        **kwargs,
    ):
        if style is None:
            style = {}
        self._cfunc = cfunc
        self._kw = kw or (lambda _: {})
        self._cancel_description = cancel_description
        self.name = description
        self._style = style
        self._button_style = button_style
        self._cancel_style = cancel_button_style
        self._tooltip = tooltip
        self._tasktype = tasktype
        self.set_description(description)
        self.add_class(CSScls.button)
        if not isinstance(parent, hasparent.HasParent):
            msg = f"parent must be an instance of HasParent not {type(parent)}"
            raise TypeError(msg)
        super().__init__(parent=parent, style=style, tooltip=tooltip, button_style=button_style, **kwargs)
        self._taskname = f"async_run_button_{id(self)}_[{self.cfunc}]"
        self.on_click(self._on_click)
        if self.parent:
            self.log = self.parent.log
        if link_button:
            if not isinstance(self.cfunc, AsyncRunButton):
                msg = "When `link_button` cfunc must resolve to be a AsyncRunButton."
                raise TypeError(msg)
            utils.weak_observe(self.cfunc, self._update_link_button, "task")
            self._update_link_button()

    @traitlets.validate("name")
    def _hp_validate_name(self, proposal):
        if self.disabled:
            msg = "Cannot set name when disabled!"
            raise RuntimeError(msg)
        value = super()._hp_validate_name(proposal)
        if self.description == self.name:
            self.set_description(value)
        return value

    @traitlets.observe("task")
    def _observe_task(self, _):
        if self.task:
            self.tooltip = f"Cancel\n Task name is: {self.task.get_name()}"
            self.button_style = self._cancel_style
            self.set_description(self._cancel_description)
        else:
            self.set_description(self.name)
            self.tooltip = self._tooltip
            self.button_style = self._button_style

    @property
    def kw(self) -> dict:
        return self._kw(self.parent)

    @property
    def cfunc(self):
        return self._cfunc(self.parent)  # type: ignore

    def _update_link_button(self):
        if getattr(self.cfunc, "task", None):
            if not self.task:
                self.disabled = True
                self._update_disabled = True
        elif self._update_disabled:
            self._update_disabled = False
            self.disabled = False

    def _on_click(self, _: ipw.Button):  # type: ignore
        if self.task:
            self.cancel()
        else:
            self.start()

    def set_description(self, value: str):
        self.set_trait("description", value)

    def _done_callback(self, task: asyncio.Task):
        "Task done callback"
        if task is self.task:
            self.set_trait("task", None)

    @log_exceptions
    def _start(self, restart=True, *, task: asyncio.Task | None = None, **kwargs):
        coro_mode = bool(task)
        if self.disabled:
            msg = f"'{self}' is disabled!"
            raise RuntimeError(msg)
        if not restart and self.task and not self.task.cancelling():
            if task and task is self.task:
                msg = f"Recursive call to {self}"
                raise RecursionError(msg)
            return self.task
        kw = self.kw | kwargs
        cfunc = self.cfunc
        if isinstance(cfunc, AsyncRunButton):
            aw = cfunc.start(restart=restart, task=task, **kw)
            if isinstance(aw, asyncio.Task):
                task = aw
        else:
            aw = self._get_runner(cfunc, kw)
        if not task:
            task = mb_async.run_async_singular(
                aw, obj=self, tasktype=self._tasktype, name=self._taskname, restart=restart
            )
        if not task.done():
            if task is not self.task:
                self.set_trait("task", task)
                task.add_done_callback(self._done_callback)
            if self.parent and task not in self.parent.tasks:
                self.parent.tasks.add(task)
                task.add_done_callback(self.parent.tasks.discard)
        if task not in self.tasks:
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        return (aw() if callable(aw) else aw) if coro_mode else task

    def _get_runner(self, coro, kw: dict):
        async def _run_async(kw=kw):
            return await coro(**kw)

        return _run_async

    def start(self, restart=True, **kwargs) -> asyncio.Task:
        """Start always unless restart=False.

        restart=True:
            Will restart if already running.
        restart=False:
            Will start the task only if it isn't running.
        **kwargs are passed to async function to override existing arguments.
        """
        return self._start(restart=restart, **kwargs)  # type: ignore

    def start_wait(self, restart=True, **kwargs) -> Coroutine:
        "Same as start but returns a coroutine and uses the current task."
        return self._start(restart=restart, task=asyncio.current_task(), **kwargs)  # type: ignore

    def cancel(self, force=False, message=""):
        """Schedule cancel if already running.
        force: if task is already being cancelled force will call cancel again.
        """
        if self.task and (force or not self.task.cancelling()):
            self.task.cancel(message or f'Cancelled by call to cancel of :"{self}"')

    async def cancel_wait(self, force=False, message=""):
        if self.task:
            self.cancel(force, message=message)
            await asyncio.sleep(0)
            if self.task:
                # permit on cycle for cleanup
                await asyncio.sleep(0)
            if self.task:
                self.log.info('Waiting until task "%s" is done.', self.task.get_name())
                await asyncio.wait([self.task])
