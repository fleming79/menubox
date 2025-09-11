from __future__ import annotations

import contextlib
from collections.abc import Callable
from types import CoroutineType
from typing import TYPE_CHECKING, Any, Generic, Literal, cast, override

import anyio
import ipywidgets as ipw
import traitlets

from menubox import hasparent, mb_async, utils
from menubox.css import CSScls
from menubox.hasparent import HasParent
from menubox.trait_factory import TF
from menubox.trait_types import ChangeType, S

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import CoroutineType

    from async_kernel import Future


class AsyncRunButton(HasParent, ipw.Button, Generic[S]):
    """A button that runs the function in a singular task that can be cancelled by
    clicking the button again.

    Additional methods are added to the button `start`, `cancel`, `cancel_wait` which
    control the button action. The active task is added as the attribute `task`.

    parent: HasParent | None
        Parent is passed as obj to run_async.
    c_func: async | AsyncRunButton | str
        This is the function or AsyncRunButton to call with kw. Noting that the tasks
        are linked, so cancelling one will cancel the other. Strings are also accepted
        with dotted name access relative to parent.
    kw : dict | callable
    If kw is callable, it will be called when the button is clicked.  It must return a
    dict.
    """

    _update_disabled = False
    description = traitlets.Unicode(read_only=True).tag(sync=True)
    task = TF.Future()
    parent = TF.parent(cast(type[S], HasParent))

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
        tasktype: mb_async.TaskType = mb_async.TaskType.general,
        **kwargs,
    ):
        if style is None:
            style = {}
        self._cfunc = cfunc
        self._kw: Callable[[S], dict[Any, Any]] | Callable[..., dict[Any, Any]] = kw or (lambda _: {})
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
        self.on_click(self._on_click)
        self.log = self.parent.log
        if isinstance(b := self._cfunc(self.parent), AsyncRunButton):
            utils.weak_observe(b, self._observe_main_button_task, "task", pass_change=True)
            self.set_trait("task", b.task)

    @traitlets.validate("name")
    def _hp_validate_name(self, proposal):
        if self.disabled:
            msg = "Cannot set name when disabled!"
            raise RuntimeError(msg)
        value = super()._hp_validate_name(proposal)
        if self.description == self.name:
            self.set_description(value)
        return value

    @property
    def kw(self) -> dict:
        assert self.parent  # noqa: S101
        return self._kw(self.parent)

    @traitlets.observe("task")
    def _observe_task(self, change: ChangeType):
        if parent := self.parent:
            if change["new"]:
                parent.tasks.add(change["new"])
            if change["old"]:
                parent.tasks.discard(change["old"])
        if self.task:
            self.button_style = self._cancel_style
            self.set_description(self._cancel_description)
        else:
            self.set_description(self.name)
            self.tooltip = self._tooltip
            self.button_style = self._button_style

    def _observe_main_button_task(self, change: ChangeType):
        fut: Future | None = change["new"]
        self.set_trait("task", fut)
        if fut:
            self.tasks.add(fut)
            fut.add_done_callback(self.tasks.discard)
            if parent := self.parent:
                parent.tasks.add(fut)
                fut.add_done_callback(parent.tasks.discard)

    def _on_click(self, _: ipw.Button):  # type: ignore
        if self.task:
            self.cancel(message="Button clicked to cancel")
        else:
            self.start()

    def set_description(self, value: str):
        self.set_trait("description", value)

    def _done_callback(self, fut: Future):
        if fut is self.task:
            self.set_trait("task", None)
        self.parent.tasks.discard(fut)

    def start(self, restart=True, /, *args, **kwargs) -> Future:
        """Start always unless restart=False."""
        if self.disabled:
            msg = f"'{self}' is disabled!"
            raise RuntimeError(msg)
        btn, cfunc = self, self._cfunc(self.parent)
        while isinstance(cfunc, AsyncRunButton):
            btn, cfunc = cfunc, cfunc._cfunc(cfunc.parent)
        key = btn, cfunc
        if not restart and (fut := mb_async.singular_tasks.get(key)) and (not fut.cancelled()):
            return fut
        opts = mb_async.RunAsyncOptions(obj=self.parent, tasktype=self._tasktype, restart=restart, key=key)
        fut = mb_async.run_async(opts, cfunc, *args, **self.kw | kwargs)
        btn.set_trait("task", fut)
        fut.add_done_callback(btn._done_callback)
        return fut

    def cancel(self, force=False, message=""):
        """Schedule cancel if already running.
        force: if task is already being cancelled force will call cancel again.
        """
        if self.task and (force or not self.task._cancelled):
            self.task.cancel(f'Cancelled by call to cancel of :"{self}"')

    async def cancel_wait(self, force=False, msg="Waiting for future to cancel."):
        if task := self.task:
            while not task.done():
                with anyio.move_on_after(1):
                    self.log.info(msg)
                    task.cancel(msg)
                    with contextlib.suppress(Exception):
                        await task

    @override
    def on_error(self, error: BaseException, msg: str, obj: Any = None) -> None:
        self.parent.on_error(error, msg, obj)
