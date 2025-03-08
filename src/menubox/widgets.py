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

from menubox import mb_async

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
    _bi_validate: weakref.ref | None = None

    @traitlets.validate("value")
    def _validate_value(self, proposal: ProposalType):
        if self._skip_validate:
            return proposal["value"]
        return self.validate(proposal["value"])

    def __init__(self, *, validate: None | Callable[[ProposalType], Any] = None, **kwargs):
        if validate:
            if inspect.ismethod(validate):
                self._bi_validate = weakref.WeakMethod(validate)
            else:
                self._bi_validate = weakref.ref(validate)

        super().__init__(**kwargs)

    def set_state(self, sync_data):
        if isinstance(sync_data, dict) and "value" in sync_data:
            # Validate the incoming data from the frontend
            fe_value = self._trait_from_json(sync_data["value"], self)
            try:
                # Perform validation prior to setting it with the traitlets machinery making it straight forward
                # to revert the original value back to the frontend should the validation fail.
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
        return v(x) if self._bi_validate and (v := self._bi_validate()) else x


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
                self.push(ipd.Markdown(self._converted_value, url=self.url or None), clear=True)

    @mb_async.debounce(1)
    def update(self):
        self._converted_value = self.converter(self.value)
