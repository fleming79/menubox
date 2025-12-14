from __future__ import annotations

import contextlib
import weakref
from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    NotRequired,
    Self,
    TypedDict,
    Unpack,
    override,
)

from ipywidgets import Widget
from mergedeep import Strategy, merge
from traitlets import TraitType

import menubox as mb
from menubox import defaults, utils
from menubox.hasparent import HasParent
from menubox.instance import IHPChange, IHPCreate, IHPSet, InstanceHP
from menubox.trait_types import T, V
from menubox.valuetraits import ValueTraits

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from types import UnionType

    from menubox.trait_types import ChangeType


class InstanceHPTupleHookMappings(TypedDict, Generic[V, T]):
    update_by: NotRequired[str]
    update_item_names: NotRequired[tuple[str, ...]]
    set_parent: NotRequired[bool]
    close_on_remove: NotRequired[bool]
    on_add: NotRequired[Callable[[IHPSet[V, T]], Any]]
    on_remove: NotRequired[Callable[[IHPSet[V, T]], Any]]
    value_changed: NotRequired[Callable[[IHPChange[V, T]], None]]


class InstanceHPTuple(InstanceHP[V, tuple[T, ...], tuple[T, ...]], Generic[V, T]):
    """A tuple for `ValueTraits` where elements can be spawned and observed.

    This class provides a way to manage a tuple of instances within a ValueTraits
    object. It allows for the creation, validation, and updating of instances
    within the tuple, as well as the execution of callbacks when instances are
    added or removed.
    The key features include:
    - **Type Safety:** Enforces that all elements in the tuple are of the same
      type, as defined by the provided TraitType.
    - **Instance Management:** Can automatically create new instances based on
      dictionary input, update existing instances based on a specified key, and
      set the parent of new instances to the ValueTraits object.
    - **Callbacks:** Supports callbacks for when instances are added or removed
      from the tuple.
    - **Validation:** Validates each element added to the tuple using the
      TraitType's validation logic.
    - **Configuration:** Offers extensive configuration options to control the
      behavior of the tuple, such as whether to spawn new instances, how to
      update existing instances, and whether to set the parent of new instances.

    Type hints:

    Perform type hinting directly on the class.

    ```
    class MyClass(ValueTraits):
        ihp_tuple = InstanceHPTuple[Self, str](trait=UniCode(), ...
    ```
    """

    default_value = ()
    info_text = "A tuple that can spawn new instances"  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType]
    validating = False
    if TYPE_CHECKING:
        _hookmappings: InstanceHPTupleHookMappings[V, T]  # pyright: ignore[reportIncompatibleVariableOverride]

        def __new__(
            cls,
            klass: type[T] | str | UnionType,
            *,
            default: Callable[[IHPCreate[V, T]], tuple[T, ...]] = ...,
            factory: Callable[[IHPCreate[V, T]], T] | None = ...,
            default_value: tuple[T, ...] = ...,
            read_only: bool = ...,
            co_: V | Any = ...,
        ) -> InstanceHPTuple[V, T]: ...

    @contextlib.contextmanager
    def _busy_validating(self):
        self.validating = True
        try:
            yield
        finally:
            self.validating = False

    def __set_name__(self, owner: ValueTraits, name: str):
        # Register this tuplename with owner (class)
        self.name = name
        d = dict(owner._InstanceHPTuple or {})
        if not owner._InstanceHPTuple:
            # Check for inheritance from other classes
            for cls in owner.__class__.mro(owner.__class__):  # pyright: ignore[reportCallIssue]
                if issubclass(cls, ValueTraits) and cls._InstanceHPTuple:
                    d.update(cls._InstanceHPTuple)
        owner._InstanceHPTuple = d | {name: self}  # pyright: ignore[reportAttributeAccessIssue]

    @staticmethod
    def _all_traits(obj):
        if hasattr(obj, "_trait"):
            if hasattr(obj._trait, "trait_types"):
                for obj_ in obj._trait.trait_types:
                    yield from InstanceHPTuple._all_traits(obj_)
            else:
                yield obj._trait
        if isinstance(obj, TraitType):
            yield obj

    def __init__(
        self,
        klass: type[T] | str | UnionType,
        *,
        default: Callable[[IHPCreate[V, T]], tuple[T, ...]] = lambda _: (),
        factory: Callable[[IHPCreate[V, T]], T] | None = lambda c: c["klass"](
            **c["kwgs"]
        ),
        default_value: tuple[T, ...] = (),
        read_only=False,
        co_: V | Any = None,
    ):
        """A tuple style trait where elements can be spawned and observed with ValueTraits.on_change."""
        self.trait = InstanceHP(
            klass, lambda _: "Default should not be called for InstanceHPTuple.trait"
        )  # pyright: ignore[reportCallIssue, reportArgumentType]
        if factory and not callable(factory):
            msg = "factory must be callable!"
            raise TypeError(msg)
        super().__init__(klass, default, default_value=default_value, co_=co_)  # pyright: ignore[reportArgumentType]
        self._factory = factory
        self.read_only = read_only
        self._close_observers: weakref.WeakKeyDictionary[T, (Callable, str)] = (
            weakref.WeakKeyDictionary()
        )  # pyright: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]

    def class_init(self, cls: type[Any], name: str | None) -> None:
        super().class_init(cls, name)
        self.trait.class_init(cls, None)

    def subclass_init(self, cls: type[Self]):  # pyright: ignore[reportIncompatibleMethodOverride]
        if not issubclass(cls, ValueTraits):
            msg = "InstanceHPTuple is only compatible with ValueTraits or a subclass."
            raise TypeError(msg)
        super().subclass_init(cls)
        # Required to ensure instance_init is always called during init
        if (
            hasattr(cls, "_instance_inits")
            and self.instance_init not in cls._instance_inits
        ):
            cls._instance_inits.append(self.instance_init)

    def instance_init(self, obj: V):
        """Init an instance of InstanceHPTuple."""
        self.trait.instance_init(obj)
        super().instance_init(obj)
        utils.weak_observe(obj, self._on_change, names=self.name, pass_change=True)

    def _validate(self, obj: V, value: Iterable) -> tuple[T, ...]:
        if obj.closed:
            return ()
        try:
            if self.validating:
                return (
                    getattr(obj, self.name)
                    if obj.trait_has_value(self.name)
                    else self.default_value
                )
            with self._busy_validating():
                values = []
                for i, v in enumerate(value):
                    val = v
                    try:
                        val = self.trait._validate(obj, val)
                    except Exception as e:
                        if isinstance(val, dict):
                            val = self.update_or_create_inst(obj, val, i)
                        elif self._hookmappings.get("update_by") == defaults.INDEX:
                            values = getattr(obj, self.name)
                            obj.setter(values[i], "value", v)
                            continue
                        else:
                            e.add_note(f"`{obj.__class__.__name__}.{self.name}` {obj=}")
                            raise
                    if val is None:
                        continue
                    if id(val) not in map(id, values) and not getattr(
                        val, "closed", False
                    ):
                        values.append(val)
                return tuple(values)
        except Exception as e:
            obj.on_error(e, "Trait validation error", self)
            raise

    def update_or_create_inst(self, obj: V, kw: dict, index=None) -> T:
        if (inst := self._find_update_item(obj, kw, index=index)) is not None:
            return inst
        try:
            return self.create_inst(obj, kw)
        except Exception:
            if mb.DEBUG_ENABLED:
                raise
            raise

    def create_inst(self, obj: V, kw: dict) -> T:
        "Create a new instance using the factory"
        if not self._factory:
            msg = f"Cannot create a new instance because a factory is not specified for {self!r}"
            raise RuntimeError(msg)
        kw = {"parent": obj} | kw if self._hookmappings.get("set_parent", False) else kw
        c = IHPCreate(
            name=self.name, owner=obj, klass=self.trait.finalize().klass, kwgs=kw
        )
        inst = self._factory(c)
        self.trait._validate(obj, inst)
        return inst

    def _find_update_item(self, obj, kw: dict, index: int | None) -> T | None:
        """Check if an item exists in current tuple matching update_by in kw.

        The first inst found is updated with kw and returned.
        """
        ub = self._hookmappings.get("update_by", "name")
        if not ub:
            return None
        if ub is defaults.INDEX:
            if index is None:
                return None
        elif ub not in kw:
            return None
        current: tuple[T, ...] = getattr(obj, self.name)
        for i, inst in enumerate(current):
            if index is not None and ub is defaults.INDEX:
                if i < index:
                    continue
            else:
                ub_ = utils.getattr_nested(inst, ub, hastrait_value=True)
                if ub_ != kw[ub]:
                    continue
            default_setter = getattr(inst, "setter", obj.setter)
            if isinstance(inst, ValueTraits):
                inst.value = kw
            else:
                for k, v in kw.items():
                    if k == ub:
                        continue
                    utils.setattr_nested(inst, k, v, default_setter=default_setter)
            return inst
        return None

    @override
    def hooks(self, **kwgs: Unpack[InstanceHPTupleHookMappings[V, T]]) -> Self:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Hooks to modify the behaviour of the tuple analogous to hooks in InstanceHP.

        kwgs
        ----

        - update_by: An optional string specifying the attribute to use when updating items.
        - update_item_names: An optional tuple of strings specifying the item names to update.
        set_parent: An optional boolean indicating whether to set the parent of added items.
        - close_on_remove: An optional boolean indicating whether to close items when they are removed.
        - on_add: An optional callable that is executed when an item is added to the tuple.
               It takes the IHPSet as an argument.
        - on_remove: An optional callable that is executed when an item is removed from the tuple.
                  It takes the IHPSet as an argument.
        - value_changed: An optional callable that is executed when the value of an tuple changes.
                       It takes an IHPChange object as an argument.

        Tip:
            To support restoring values by index for a instances of objects that aren't subclassed
            from ValueTraits, but have a `value` trait: use the hook `update_by = menubox.defaults.INDEX`."""
        if kwgs:
            merge(self._hookmappings, kwgs, strategy=Strategy.REPLACE)  # pyright: ignore[reportArgumentType]
        return self

    def _on_add(self, obj: V, value: T):
        if isinstance(value, HasParent) and self._hookmappings.get("set_parent"):
            value.parent = obj
        if isinstance(value, HasParent | Widget) and value not in self._close_observers:
            names = "closed" if isinstance(value, HasParent) else "comm"
            handle = utils.weak_observe(
                value, self._observe_obj_closed, names, False, weakref.ref(obj), names
            )
            self._close_observers[value] = handle, names
        if on_add := self._hookmappings.get("on_add"):
            try:
                on_add(IHPSet(name=self.name, owner=obj, obj=value))
            except Exception as e:
                obj.on_error(e, f"on_add callback for {self!r}")

    def _on_remove(self, obj: V, value: T):
        if isinstance(value, HasParent | Widget) and (
            args := self._close_observers.pop(value, None)
        ):
            value.unobserve(*args)
        if self._hookmappings.get("close_on_remove") and hasattr(value, "close"):
            value.close()  # pyright: ignore[reportAttributeAccessIssue]
        if on_remove := self._hookmappings.get("on_remove"):
            try:
                on_remove(IHPSet(name=self.name, owner=obj, obj=value))
            except Exception as e:
                obj.on_error(e, msg=f"on_remove callback for {self!r}")

    def tag(self, **kw):
        raise NotImplementedError

    def _observe_obj_closed(self, ref: weakref.ref[V], name: str):
        if (parent := ref()) and not parent.closed:
            filt = (
                (lambda obj: not obj.closed)
                if name == "closed"
                else lambda obj: obj.comm
            )
            values = filter(filt, getattr(parent, self.name))
            parent.set_trait(self.name, values)

    def _on_change(self, change: ChangeType):
        # Collect pairs and update register
        obj: V = change["owner"]  # pyright: ignore[reportAssignmentType]
        if obj.closed:
            return
        obj._vt_update_reg_tuples(self.name)
        new, old = change["new"], change["old"]

        for value in set(old).difference(new):
            self._on_remove(obj, value)
        for value in set(new).difference(old):
            self._on_add(obj, value)
