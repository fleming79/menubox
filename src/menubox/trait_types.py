from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal, TypedDict, TypeVar

import toolz
import traitlets

T = TypeVar("T")

__all__ = ["Bunched", "NameTuple", "StrTuple", "TypedTuple", "ChangeType", "ProposalType"]


class ChangeType(TypedDict):
    new: Any
    old: Any
    name: str
    owner: traitlets.HasTraits
    type: Literal["change"]


class ProposalType(TypedDict):
    trait: traitlets.TraitType
    value: Any
    owner: traitlets.HasTraits


class Bunched(traitlets.Bunch):
    """A distinct bunch (hashable)"""

    def __hash__(self):  # type: ignore
        # hash here should be distinct
        # for other hash ideas: https://stackoverflow.com/questions/1151658/python-hashable-dicts#1151705
        return id(self)


class TypedTuple(traitlets.TraitType[tuple[T, ...], Iterable[T]]):
    name: str  # type: ignore
    info_text = "A trait for a tuple of any length with type-checked elements."

    def __init__(self, trait: traitlets.TraitType[T, T], default_value=(), **kwargs: Any) -> None:
        if not isinstance(trait, traitlets.TraitType):
            msg = f"{trait=} is not a TraitType"
            raise TypeError(msg)
        self._trait = trait
        super().__init__(default_value, **kwargs)

    def class_init(self, cls: type[Any], name: str | None) -> None:
        self._trait.class_init(cls, None)
        super().class_init(cls, name)

    def subclass_init(self, cls: type[Any]) -> None:
        if isinstance(self._trait, traitlets.TraitType):
            self._trait.subclass_init(cls)

    def instance_init(self, obj: Any) -> None:
        self._trait.instance_init(obj)
        return super().instance_init(obj)

    def validate(self, obj, value):
        return tuple(self._trait._validate(obj, v) for v in value)


class StrTuple(traitlets.TraitType[tuple[str, ...], Iterable[str]]):
    "A Trait for a tuple of strings."

    info_text = "A tuple of any length of str."
    name: str  # type: ignore
    _trait_klass = traitlets.Unicode
    default_value: tuple[str, ...] = ()

    def __iter__(self):
        yield from self.default_value

    def __init__(self, *default_value, **kwargs):
        """A Tuple of strings of any length."""
        self._trait = self._trait_klass()
        super().__init__(default_value, **kwargs)

    def validate(self, obj, value):
        return tuple(self._iterate(self._trait._validate(obj, v) for v in value)) if value else ()

    def _iterate(self, value):
        yield from value


class NameTuple(StrTuple):
    """A Trait for a tuple of unique dotted object names."""

    info_text = "A tuple of any length of unique object trait_names (duplicates discarded.)"
    _trait_klass = traitlets.DottedObjectName

    def _iterate(self, value):
        yield from toolz.unique(value)
