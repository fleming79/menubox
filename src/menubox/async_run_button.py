from __future__ import annotations

from collections.abc import Callable
from types import CoroutineType
from typing import TYPE_CHECKING, Any, Generic, Literal, override

import ipywidgets as ipw
from traitlets import traitlets

from menubox import hasparent, mb_async, utils
from menubox.css import CSScls
from menubox.hasparent import HasParent
from menubox.trait_factory import TF
from menubox.trait_types import ChangeType, S, S_co

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import CoroutineType

    from async_kernel import Pending

    from menubox.instance import InstanceHP


class AsyncRunButton(HasParent[S_co], ipw.Button, Generic[S_co]):
    """
    A button that runs the function in a singular pen that can be cancelled by
    clicking the button again.

    Additional methods are added to the button `start`, `cancel`, `cancel_wait` which
    control the button action. The active pen is added as the attribute `pen`.

    parent: HasParent | None
        Parent is passed as obj to run_async.
    c_func: async | AsyncRunButton | str
        This is the function or AsyncRunButton to call with kw. Noting that the pending
        are linked, so cancelling one will cancel the other. Strings are also accepted
        with dotted name access relative to parent.
    kw : dict | callable
    If kw is callable, it will be called when the button is clicked.  It must return a
    dict.
    """

    _update_disabled = False
    pen = TF.Pending()
    parent: InstanceHP[Any, S_co] = TF.parent().configure(TF.IHPMode.X___)  # pyright: ignore[reportIncompatibleVariableOverride]

    def __new__(
        cls,
        cfunc: Callable[[S_co], Callable[..., CoroutineType] | AsyncRunButton],
        parent: S_co,
        **kwargs,
    ):
        return super().__new__(cls, parent=parent, cfunc=cfunc, **kwargs)

    def __init__(
        self,
        cfunc: Callable[[S_co], Callable[..., CoroutineType] | AsyncRunButton],
        *,
        parent: S_co,
        description="",
        icon="play",
        cancel_icon="stop",
        kw: Callable[[S], dict] | None = None,
        style: dict | None = None,
        button_style: Literal["primary", "success", "info", "warning", "danger", ""] = "primary",
        cancel_button_style: Literal["primary", "success", "info", "warning", "danger", ""] = "warning",
        tooltip="",
        penptype: mb_async.PenType = mb_async.PenType.general,
        **kwargs,
    ):
        if style is None:
            style = {}
        self._cfunc = cfunc
        self._kw: Callable[[S_co], dict[Any, Any]] | Callable[..., dict[Any, Any]] = kw or (lambda _: {})
        self._icon = icon
        self._cancel_icon = cancel_icon
        self._style = style
        self._button_style = button_style
        self._cancel_style: Literal["primary", "success", "info", "warning", "danger", ""] = cancel_button_style
        self._tooltip = tooltip
        self._pentype = penptype
        self.add_class(CSScls.button)
        if not isinstance(parent, hasparent.HasParent):
            msg = f"parent must be an instance of HasParent not {type(parent)}"
            raise TypeError(msg)
        super().__init__(
            parent=parent,
            style=style,
            tooltip=tooltip,
            button_style=button_style,
            description=description,
            icon=icon,
            **kwargs,
        )
        self.on_click(self._on_click)
        self.log = self.parent.log
        if isinstance(b := self._cfunc(self.parent), AsyncRunButton):
            utils.weak_observe(b, self._observe_main_button_pen, "pen", pass_change=True)
            self.set_trait("pen", b.pen)

    @property
    def kw(self) -> dict:
        assert self.parent
        return self._kw(self.parent)

    @traitlets.observe("pen")
    def _observe_pen(self, change: ChangeType):
        if parent := self.parent:
            if change["new"]:
                parent.pending.add(change["new"])
            if change["old"]:
                parent.pending.discard(change["old"])
        if self.pen:
            self.button_style = self._cancel_style
            self.icon = self._cancel_icon
        else:
            self.icon = self._icon
            self.tooltip = self._tooltip
            self.button_style = self._button_style

    def _observe_main_button_pen(self, change: ChangeType):
        pen: Pending | None = change["new"]
        self.set_trait("pen", pen)
        if pen:
            self.pending.add(pen)
            pen.add_done_callback(self.pending.discard)
            if parent := self.parent:
                parent.pending.add(pen)
                pen.add_done_callback(parent.pending.discard)

    def _on_click(self, _: ipw.Button):  # pyright: ignore[reportIncompatibleMethodOverride]
        if self.pen:
            self.cancel("Button clicked to cancel")
        else:
            self.start(True)

    def _done_callback(self, pen: Pending):
        if pen is self.pen:
            self.set_trait("pen", None)

    def start(self, restart: bool, /, *args, **kwargs) -> Pending:  # pyright: ignore[reportGeneralTypeIssues]
        """
        Start the associated coroutine.

        Args:
            restart:
        """
        if self.disabled:
            msg = f"'{self}' is disabled!"
            raise RuntimeError(msg)
        btn, cfunc = self, self._cfunc(self.parent)
        while isinstance(cfunc, AsyncRunButton):
            btn, cfunc = cfunc, cfunc._cfunc(cfunc.parent)
        key = btn, cfunc
        if not restart and (pen := mb_async.singular_pending.get(key)) and (not pen.cancelled()):
            return pen
        opts = mb_async.RunAsyncOptions(obj=self.parent, pentype=self._pentype, restart=restart, key=key)
        pen = mb_async.run_async(opts, cfunc, *args, **self.kw | kwargs)
        btn.set_trait("pen", pen)
        pen.add_done_callback(btn._done_callback)
        return pen

    def cancel(self, msg=""):
        """
        Cancel the pen if there is one.

        Args:
            force: If the pen is already being cancelled force will call cancel again.
            message: The message.
        """
        if pen := self.pen:
            pen.cancel(msg or f'Cancelled by call to cancel of :"{self}"')

    async def cancel_wait(self, msg="Cancelled by cancel_wait", timeout: float | None = None):
        if pen := self.pen:
            pen.cancel(msg)
            await pen.wait(result=False, timeout=timeout)

    @override
    def on_error(self, error: BaseException, msg: str, obj: Any = None) -> None:
        self.parent.on_error(error, msg, obj)
