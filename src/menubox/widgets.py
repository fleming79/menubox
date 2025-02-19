"""Additional widgets not defined in IpyWidgets."""

from __future__ import annotations

import asyncio
import functools
import inspect
import weakref
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import ipylab
import ipywidgets as ipw
import traitlets
from IPython import display as ipd

from menubox import hasparent, trait_types, utils
from menubox.instance import InstanceHP
from menubox.log import log_exceptions

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from menubox.trait_types import ChangeType, ProposalType

__all__ = [
    "AsyncRunButton",
    "ComboboxValidate",
    "FloatTextValidate",
    "IntTextValidate",
    "MarkdownViewer",
    "SelectMultipleValidate",
    "TextValidate",
    "TextareaValidate",
    "ValidatedTrait",
    "ValidateWidget",
]


class ValidatedTrait(traitlets.TraitType):
    "A trait that validates the trait by calling the method."

    def _validate(self, obj: ValidateWidget, value: Any):
        return obj.validate(value)


class ValidateWidget(ipw.ValueWidget):
    """Widget with custom bi-directional validation of the value.

    validate:
        A callable that accepts a value and returns another value, or raises an error
        if the value is invalid. If overloading, validate could be:
        1. overridden as a method, or
        2. specified using dynamic default with [traitlets.default](https://traitlets.readthedocs.io/en/stable/api.html#dynamic-default-values).

    Note: A weakref is maintained to the validate function.
    If subclassing, validate can be overloaded directly.
    """

    _skip_validate = False
    value = ValidatedTrait().tag(sync=True)
    _validate: weakref.ref | None = None

    @traitlets.validate("value")
    def _validate_value(self, proposal: ProposalType):
        if self._skip_validate:
            return proposal["value"]
        return self.validate(proposal["value"])

    def __init__(self, *, validate: None | Callable[[ProposalType], Any] = None, **kwargs):
        if validate:
            if inspect.ismethod(validate):
                self._validate = weakref.WeakMethod(validate)
            else:
                self._validate = weakref.ref(validate)

        super().__init__(**kwargs)

    def set_state(self, sync_data):
        if isinstance(sync_data, dict) and "value" in sync_data:
            # Validate the incoming data from the frontend
            try:
                # Perform validation prior to setting it with the traitlets machinery making it straight forward
                # to revert the original value back to the frontend should the validation fail.
                fe_value = self._trait_from_json(sync_data["value"], self)
                sync_data["value"] = self._trait_to_json(self.validate(fe_value), self)
                self._skip_validate = True
                super().set_state(sync_data)
            except Exception:
                self.log.warning(
                    "Validation failed for value= {fe_value}. Reverting state in the frontend.",
                    extra={"fe_value": fe_value},
                )
                self.send_state(tuple(sync_data))
            finally:
                self._skip_validate = False
        else:
            super().set_state(sync_data)

    def validate(self, x):
        return v(x) if self._validate and (v := self._validate()) else x


class TextareaValidate(ipw.Textarea, ValidateWidget):
    continuous_update = traitlets.Bool(False).tag(sync=True)
    value = ValidatedTrait().tag(sync=True)


class TextValidate(ipw.Text, ValidateWidget):
    continuous_update = traitlets.Bool(False).tag(sync=True)
    value = ValidatedTrait().tag(sync=True)


class ComboboxValidate(ipw.Combobox, ValidateWidget):
    continuous_update = traitlets.Bool(False).tag(sync=True)
    value = ValidatedTrait().tag(sync=True)


class FloatTextValidate(ipw.FloatText, ValidateWidget):
    value = ValidatedTrait().tag(sync=True)


class IntTextValidate(ipw.IntText, ValidateWidget):
    value = ValidatedTrait().tag(sync=True)


class SelectMultipleValidate(ipw.SelectMultiple, ValidateWidget):
    "SelectMultiple that drops values not in options for validation by default."

    value = ValidatedTrait().tag(sync=True)
    options: tuple

    def __init__(self, *, validate: None | Callable[[ProposalType], Any] = None, **kwargs):
        super().__init__(validate=validate or self._validate_value_default, **kwargs)

    def _validate_value_default(self, value):
        try:
            return tuple(v for v in value if v in self.options)
        except Exception:
            return ()


class MarkdownViewer(ipylab.SimpleOutput):
    _converted_value = traitlets.Unicode()
    value = traitlets.Unicode()
    max_outputs = traitlets.Int(1).tag(sync=True)
    converter = traitlets.Callable(lambda value: value)
    url = traitlets.Unicode()

    @traitlets.observe("value", "_converted_value")
    def _observe_value(self, change: ChangeType):
        match change["name"]:
            case "value":
                if not self._converted_value:
                    self._converted_value = self.converter(self.value)
                else:
                    self.update()
            case "_converted_value":
                self.push(ipd.Markdown(self._converted_value, url=self.url or None))

    @utils.debounce(1)
    def update(self):
        self._converted_value = self.converter(self.value)


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
    disable_when_sub_button_runs:
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
        handle: str | None = None,
        disable_when_sub_button_runs=False,
        tasktype: utils.TaskType = utils.TaskType.general,
        parent: hasparent.HasParent | None = None,
        **kwargs,
    ):
        if style is None:
            style = {}
        if kw is None:
            kw = {}
        if handle and parent is None:
            msg = f"handle' is only relevant when a parent is provided. {handle=}."
            raise TypeError(msg)
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
        self._handle = handle
        self._tasktype = tasktype
        if callable(cfunc):
            detail = f"[{utils.funcname(cfunc)}]"
        elif isinstance(cfunc, AsyncRunButton):
            detail = "[" + cfunc._taskname.split("_[", maxsplit=1)[1]
        else:
            msg = "Not sure what to do with cfunc"
            raise TypeError(msg)
        self._taskname = f"async_run_button_{id(self)}_{detail}"
        if disable_when_sub_button_runs:
            if not isinstance(self._corofunc_or_button, AsyncRunButton):
                msg = "When `disable_when_sub_button_runs` cfunc must resolve to an AsyncRunButton."
                raise TypeError(msg)
            self._corofunc_or_button.observe(self._observe_corofunc_button_task, "task")
            if cfunc.task:
                self.disabled = True
                self._update_disabled = True
        super().__init__(parent=parent, style=style, tooltip=tooltip, button_style=button_style, **kwargs)
        self.set_description(description)

        self.on_click(self.button_clicked)
        if self.parent:
            self.log = self.parent.log

    @traitlets.validate("name")
    def _hp_validate_name(self, proposal):
        if self.disabled:
            msg = f"{self} - cannot set name when disabled."
            raise RuntimeError(msg)
        if self.description == self.name:
            self.set_description(proposal["value"])
        return super()._hp_validate_name(proposal)

    def _observe_corofunc_button_task(self, change: trait_types.ChangeType):
        if change["new"]:
            if not self.task:
                self.disabled = True
                self._update_disabled = True
        elif self._update_disabled:
            self._update_disabled = False
            self.disabled = False

    def button_clicked(self, _: ipw.Button):
        if self.task:
            self.cancel()
        else:
            self.start()

    def set_description(self, value: str):
        self.set_trait("description", value)

    def _done_callback(self, task: asyncio.Task):
        "Task done callback"
        if task is self.task:
            self.set_trait("description", self.name)
            self.button_style = self._button_style
            self.tooltip = self._tooltip
            self.set_trait("task", None)

    @log_exceptions
    def _start(self, restart=True, *, task: asyncio.Task | None = None, **kwargs):
        coro_mode = bool(task)
        if self.disabled:
            msg = f"'{self}' is disabled!"
            raise RuntimeError(msg)
        if not restart and self.task:
            if task and task is self.task:
                msg = f"Recursive call to {self}"
                raise RecursionError(msg)
            return self.task
        kwargs_in = self._kw() if callable(self._kw) else self._kw
        kw = kwargs_in | kwargs
        if isinstance(self._corofunc_or_button, AsyncRunButton):
            task = self._corofunc_or_button.start(**kw)
            aw = functools.partial(asyncio.wait_for, task, None)
        else:
            aw = functools.partial(self._corofunc_or_button, **kw)
        if coro_mode and isinstance(task, asyncio.Task):
            if self.task:
                self.task.cancel()
            if not getattr(task, "tasktype", None):
                task.tasktype = self._tasktype  # type: ignore
        else:
            task = utils.run_async_singular(
                aw, obj=self.parent or self, handle=self._handle, tasktype=self._tasktype, name=self._taskname
            )
        self.set_trait("task", task)
        task.add_done_callback(self._done_callback)
        self.set_description(self._cancel_description)
        self.tooltip = f"Cancel\n Task name is: {task.get_name()}"
        self.button_style = self._cancel_style
        return aw() if coro_mode else task

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
        "Same as start but must be awaitied to run."
        return self._start(restart=restart, task=asyncio.current_task(), **kwargs)  # type: ignore

    def cancel(self, force=False):
        """Schedule cancel if already running.
        force: if task is already being cancelled force will call cancel again.
        """
        if self.task and (force or not self.task.cancelling()):
            self.task.cancel()

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
