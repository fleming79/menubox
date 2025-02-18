from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING

import ipywidgets as ipw
import traitlets

from menubox import hasparent, mb_async, utils
from menubox.instance import InstanceHP
from menubox.log import log_exceptions

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine


class AsyncRunButton(hasparent.HasParent, ipw.Button):
    """A button that runs the function in a singular task that can be cancelled by
    clicking the button again.

    Additional methods are added to the button `start`, `cancel`, `cancel_wait` which
    control the button action. The active task is added as the attribute `task`.

    parent: HasParent | None
        Parent is passed as obj to run_async_singular along with 'handle' so is where
        the handle is attached.
    c_func: async | AsyncRunButton | str
        This is the function or AsyncRunButton to call with kw. Noting that the tasks
        are linked, so cancelling one will cancel the other. Strings are also accepted
        with dotted name access relative to parent.
    handle:
        The name of either a set or attribute as used by run_async.
    link_button:
        Disable the button while the other button is running (if not called )
    kw : dict | callable
    If kw is callable, it will be called when the button is clicked.  It must return a
    dict.
    """

    _update_disabled = False
    description = traitlets.Unicode(read_only=True).tag(sync=True)
    task = InstanceHP(asyncio.Task).configure(load_default=False)
    _corofunc_or_button = traitlets.Union(
        [traitlets.Callable(), traitlets.ForwardDeclaredInstance("AsyncRunButton"), traitlets.Unicode()], read_only=True
    )

    def __new__(
        cls, cfunc: Callable[..., Coroutine] | AsyncRunButton | str, parent: hasparent.HasParent | None = None, **kwargs
    ):
        return super().__new__(cls, parent=parent, cfunc=cfunc, **kwargs)

    def __init__(
        self,
        cfunc: Callable[..., Coroutine] | AsyncRunButton | str,
        *,
        description: str = "Start",
        cancel_description: str = "Cancel",
        kw: dict | str | Callable[[], dict] | None = None,
        style: dict | None = None,
        button_style: str = "primary",
        cancel_button_style: str = "warning",
        tooltip: str = "",
        link_button=False,
        tasktype: mb_async.TaskType = mb_async.TaskType.general,
        parent: hasparent.HasParent | None = None,
        **kwargs,
    ):
        if style is None:
            style = {}
        if kw is None:
            kw = {}
        if isinstance(cfunc, str):
            cfunc = utils.getattr_nested(parent, cfunc)
        self.set_trait("_corofunc_or_button", cfunc)
        if isinstance(kw, str):
            kw = utils.getattr_nested(parent, kw)
        if callable(kw):
            self._kw = kw
        elif isinstance(kw, dict):
            self._kw = dict(kw)
        else:
            msg = "kw should be dict or callable"
            raise TypeError(msg)
        self._cancel_description = cancel_description
        self.name = description
        self._style = style
        self._button_style = button_style
        self._cancel_style = cancel_button_style
        self._tooltip = tooltip
        self._tasktype = tasktype
        if callable(cfunc):
            self._taskname = f"async_run_button_{id(self)}_[{utils.funcname(cfunc)}]"
        elif isinstance(cfunc, AsyncRunButton):
            self._taskname = cfunc._taskname
        else:
            msg = "Not sure what to do with cfunc"
            raise TypeError(msg)
        if link_button:
            if not isinstance(self._corofunc_or_button, AsyncRunButton):
                msg = "When `link_button` cfunc must resolve to be a AsyncRunButton."
                raise TypeError(msg)
            utils.weak_observe(self._corofunc_or_button, self._update_link_button, "task")
            self._update_link_button()
        self.set_description(description)
        super().__init__(parent=parent, style=style, tooltip=tooltip, button_style=button_style, **kwargs)
        self.on_click(self._on_click)
        if self.parent:
            self.log = self.parent.log

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

    def _update_link_button(self):
        if getattr(self._corofunc_or_button, "task", None):
            if not self.task:
                self.disabled = True
                self._update_disabled = True
        elif self._update_disabled:
            self._update_disabled = False
            self.disabled = False

    def _on_click(self, _: ipw.Button):
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
        kw = (self._kw() if callable(self._kw) else self._kw) | kwargs
        if isinstance(self._corofunc_or_button, AsyncRunButton):
            aw = self._corofunc_or_button.start(restart=restart, task=task, **kw)
            if isinstance(aw, asyncio.Task):
                task = aw
        else:
            aw = functools.partial(self._corofunc_or_button, **kw)
        if not task:
            task = mb_async.run_async_singular(
                aw, obj=self, tasktype=self._tasktype, name=self._taskname, restart=restart
            )
        if task is not self.task:
            self.set_trait("task", task)
            task.add_done_callback(self._done_callback)
        if self.parent and task not in self.parent.mb_tasks:
            self.parent.mb_tasks.add(task)
            task.add_done_callback(self.parent.mb_tasks.discard)
        return (aw() if callable(aw) else aw) if coro_mode else task

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

    def cancel(self, force=False):
        """Schedule cancel if already running.
        force: if task is already being cancelled force will call cancel again.
        """
        if self.task and (force or not self.task.cancelling()):
            self.task.cancel(f'Cancelled by call to cancel of :"{self}"')

    async def cancel_wait(self, force=False):
        if self.task:
            self.cancel(force)
            await asyncio.sleep(0)
            if self.task:
                # permit on cycle for cleanup
                await asyncio.sleep(0)
            if self.task:
                self.log.info('Waiting until task "%s" is done.', self.task.get_name())
                await asyncio.wait([self.task])
