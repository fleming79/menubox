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
        Parent is passed as obj to run_async_singular.
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
    fut = TF.Future()
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
            utils.weak_observe(b, self._observe_main_button_fut, "fut", pass_change=True)
            self.set_trait("fut", b.fut)

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

    @traitlets.observe("fut")
    def _observe_fut(self, change: ChangeType):
        if parent := self.parent:
            if change["new"]:
                parent.futures.add(change["new"])
            if change["old"]:
                parent.futures.discard(change["old"])
        if self.fut:
            self.button_style = self._cancel_style
            self.set_description(self._cancel_description)
        else:
            self.set_description(self.name)
            self.tooltip = self._tooltip
            self.button_style = self._button_style

    def _observe_main_button_fut(self, change: ChangeType):
        fut = change["new"]
        self.set_trait("fut", fut)
        if fut:
            self.futures.add(fut)
            fut.add_done_callback(self.futures.discard)
            if parent := self.parent:
                parent.futures.add(fut)
                fut.add_done_callback(parent.futures.discard)

    def _on_click(self, _: ipw.Button):  # type: ignore
        if self.fut:
            self.cancel(message="Button clicked to cancel")
        else:
            self.start()

    def set_description(self, value: str):
        self.set_trait("description", value)

    def _done_callback(self, fut: Future) -> None:
        if fut is self.fut:
            self.set_trait("fut", None)

    def start(self, opts: mb_async.RunAsyncOptions | None = None, /, *args, **kwargs) -> Future:
        """Start always unless restart=False."""
        opts = opts or mb_async.RunAsyncOptions()
        if self.disabled:
            msg = f"'{self}' is disabled!"
            raise RuntimeError(msg)
        restart = opts.pop("restart", True)
        obj, cfunc = self, self._cfunc(self.parent)
        while isinstance(cfunc, AsyncRunButton):
            obj, cfunc = cfunc, cfunc._cfunc(cfunc.parent)
        if not restart and (fut := mb_async.get_pending_future(obj=obj, handle="fut")) and (not fut.cancelled()):
            return fut
        opts |= mb_async.RunAsyncOptions(obj=obj, tasktype=obj._tasktype, handle="fut", restart=restart)
        return mb_async.run_async(opts, cfunc, *args, **self.kw | kwargs)

    def cancel(self, force=False, message=""):
        """Schedule cancel if already running.
        force: if task is already being cancelled force will call cancel again.
        """
        if self.fut and (force or not self.fut._cancelled):
            self.fut.cancel(f'Cancelled by call to cancel of :"{self}"')

    async def cancel_wait(self, force=False, msg="Waiting for future to cancel."):
        if fut := self.fut:
            while not fut.done():
                with anyio.move_on_after(1):
                    self.log.info(msg)
                    fut.cancel(msg)
                    with contextlib.suppress(Exception):
                        await fut

    @override
    def on_error(self, error, msg, obj=None):
        self.parent.on_error(error, msg, obj)
