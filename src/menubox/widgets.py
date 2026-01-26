"""Additional widgets not defined in IpyWidgets."""

from __future__ import annotations

import inspect
import textwrap
import weakref
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import ipylab
import ipywidgets as ipw
import traitlets
from IPython import display as ipd

import menubox
from menubox import defaults, mb_async

if TYPE_CHECKING:
    from collections.abc import Callable

    from menubox.trait_types import ChangeType, ProposalType

__all__ = [
    "ComboboxValidate",
    "FloatTextValidate",
    "IntTextValidate",
    "MarkdownOutput",
    "SelectMultipleValidate",
    "TextValidate",
    "TextareaValidate",
    "ValidateWidget",
    "ValidatedTrait",
]


class ValidatedTrait(traitlets.TraitType):
    "A trait that validates the trait by calling the method."

    def __init__(self, default_value):
        super().__init__(default_value)

    def _validate(self, obj: ValidateWidget, value: Any):
        return obj._vw_validate(value)


class ValidateWidget(ipw.ValueWidget):
    """
    Widget with custom bi-directional validation of the value.

    validate:
        A callable that accepts a value and returns another value, or raises an error
        if the value is invalid. If overloading, validate could be:
        1. overridden as a method, or
        2. specified using dynamic default with [traitlets.default](https://traitlets.readthedocs.io/en/stable/api.html#dynamic-default-values).

    If subclassing, `validate` and `check_equality` can be overloaded as methods.

    Notes:
        - `value = ValidatedTrait(None).tag(sync=True)` must be added to the subclass.
    """

    _skip_validate = False
    value = ValidatedTrait(None).tag(sync=True)
    _bi_validate: weakref.ref | None = None
    check_equality: Callable[[Any, Any], bool]

    @traitlets.validate("value")
    def _validate_value(self, proposal: ProposalType):
        if self._skip_validate:
            return proposal["value"]
        return self._vw_validate(proposal["value"])

    def __init__(
        self,
        *,
        validate: None | Callable[[ProposalType], Any] = None,
        check_equality: Callable[[Any, Any], bool] | None = None,
        **kwargs,
    ):
        if validate:
            self.set_validate_func(validate)
        if check_equality or not hasattr(self, "check_equality"):
            self.check_equality = check_equality or menubox.HasParent.check_equality

        super().__init__(**kwargs)

    def set_validate_func(self, validate: Callable):
        if inspect.ismethod(validate):
            self._bi_validate = weakref.WeakMethod(validate)
        else:
            self._bi_validate = lambda: validate  # pyright: ignore[reportAttributeAccessIssue]

    def set_state(self, sync_data):
        if isinstance(sync_data, dict) and "value" in sync_data:
            # Validate the incoming data from the frontend
            fe_value = self._trait_from_json(sync_data["value"], self)
            try:
                # Perform validation prior to setting it with the traitlets machinery making it straight forward
                # to revert the original value back to the frontend should validation fail.
                val = self._vw_validate(fe_value)
                sync_data["value"] = self._trait_to_json(val, self)
                self._skip_validate = True
                super().set_state(sync_data)
                if not self.check_equality(fe_value, val):
                    self.send_state("value")
            except Exception:
                self.log.debug(
                    f"Validation failed for value= {fe_value!r}. Reverting state in the frontend.",
                )
                self.send_state(tuple(sync_data))
            finally:
                self._skip_validate = False
        else:
            super().set_state(sync_data)

    def _vw_validate(self, x):
        return v(x) if self._bi_validate and (v := self._bi_validate()) else x


class TextareaValidate(ipw.Textarea, ValidateWidget):
    continuous_update = traitlets.Bool(False).tag(sync=True)
    value = ValidatedTrait("").tag(sync=True)


class TextValidate(ipw.Text, ValidateWidget):
    continuous_update = traitlets.Bool(False).tag(sync=True)
    value = ValidatedTrait("").tag(sync=True)


class ComboboxValidate(ipw.Combobox, ValidateWidget):
    continuous_update = traitlets.Bool(False).tag(sync=True)
    value = ValidatedTrait("").tag(sync=True)


class FloatTextValidate(ipw.FloatText, ValidateWidget):
    value = ValidatedTrait(defaults.nan).tag(sync=True)


class IntTextValidate(ipw.IntText, ValidateWidget):
    value = ValidatedTrait("").tag(sync=True)


class SelectMultipleValidate(ipw.SelectMultiple, ValidateWidget):
    "SelectMultiple that drops values not in options for validation by default."

    value = ValidatedTrait(()).tag(sync=True)
    options: tuple

    def __init__(self, *, validate: None | Callable[[ProposalType], Any] = None, **kwargs):
        super().__init__(validate=validate or self._validate_value_default, **kwargs)

    def _validate_value_default(self, value):
        try:
            return tuple(v for v in value if v in self.options)
        except Exception:
            return ()


class MarkdownOutput(ipylab.SimpleOutput):
    _converted_value = traitlets.Unicode()
    value = traitlets.Unicode()
    max_outputs = traitlets.Int(1).tag(sync=True)
    converter = traitlets.Callable(textwrap.dedent)
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
                self.push(
                    ipd.Markdown(self._converted_value, url=self.url or None),
                    clear=True,
                )

    @mb_async.debounce(1)
    async def update(self) -> None:
        self._converted_value = self.converter(self.value)


class DropdownAdd(ipw.Dropdown, ValidateWidget):
    "A dropdown that adds the value to its options when it is set."

    value = ValidatedTrait(()).tag(sync=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_validate_func(self.validate)

    def validate(self, value):
        if value is not None and value not in self.options:
            self.set_trait("options", (*self.options, value))
        return value
