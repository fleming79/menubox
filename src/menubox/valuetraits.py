from __future__ import annotations

import contextlib
import enum
import inspect
import json
import pathlib
import weakref
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, Self, overload, override

import orjson
import ruamel.yaml
from ipywidgets import Widget
from traitlets import Dict, HasTraits, Set, TraitError, TraitType, Undefined, observe

import menubox as mb
from menubox import defaults, mb_async, utils
from menubox.hasparent import HasParent
from menubox.home import Home, InstanceHome
from menubox.pack import json_default_converter, to_yaml
from menubox.trait_types import Bunched, ChangeType, NameTuple, ProposalType, R, T

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterator

    from fsspec import AbstractFileSystem


__all__ = ["TypedInstanceTuple", "ValueTraits"]



class _ValueTraitsValueTrait(TraitType[Callable[[], dict[str, Any]], str | dict[str, Any]]):
    """A trait type for handling values within a ValueTraits object.

    This trait type is responsible for setting, validating, and storing
    values associated with a specific trait name in a ValueTraits instance.
    It ensures that the value is validated through the `_load_value` method
    of the ValueTraits object before being stored.  It also handles
    notifications when the value changes.
    """

    info_text = "ValueTraits value"
    default_value = defaults.NO_VALUE

    def set(self, obj: ValueTraits, value):  # type: ignore
        try:
            if obj.vt_validating:
                return
        except AttributeError:
            # Ignore pre-init changes
            return
        new_value = self._validate(obj, value)
        assert self.name  # noqa: S101
        obj._trait_values[self.name] = new_value
        obj._notify_trait(self.name, obj._value, new_value)

    def _validate(self, obj: ValueTraits, value):
        if obj.vt_validating:
            msg = "Validation in progress!"
            raise RuntimeError(msg)
        obj.vt_validating = True
        try:
            obj._load_value(value)
            return obj._value
        finally:
            obj.vt_validating = False


class TypedInstanceTuple(TraitType[tuple[T, ...], Iterable[T | dict]]):
    """A tuple for ValueTraits where elements can be spawned and observed.

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
    """

    name: str
    default_value = ()
    info_text = "A tuple that can spawn new instances"
    validating = False
    _callback_specs: ClassVar[dict[str, tuple[str, ...]]] = {
        "_on_add": ("obj",),
        "_on_remove": ("obj",),
        "_factory": ("kwargs",),
    }

    _update_by = "name"
    _update_item_names: tuple[str, ...] = ()
    _spawn_new_instances: bool = True
    _set_parent = True
    _close_on_remove = True
    _factory = ""
    _on_add = ""
    _on_remove = ""

    @contextlib.contextmanager
    def _busy_validating(self):
        self.validating = True
        try:
            yield
        finally:
            self.validating = False

    def __set_name__(self, owner: ValueTraits, name: str):
        # Register this tuplename with owner (class)
        self.name = name  # type: ignore
        d = dict(owner._vt_tit_names)
        if not owner._vt_tit_names:
            d = {}
            # Check for inheritance from other classes
            for cls in owner.__class__.mro(owner.__class__):  # type: ignore
                if issubclass(cls, ValueTraits) and cls._vt_tit_names:
                    d.update(cls._vt_tit_names)
        owner._vt_tit_names = d | {  # type: ignore
            name: {
                "update_by": self._update_by,
                "update_item_names": self._update_item_names,
                "new_update_inst": self.new_update_inst,
                "trait": self._trait,
            }
        }

    @staticmethod
    def _all_traits(obj):
        if hasattr(obj, "_trait"):
            if hasattr(obj._trait, "trait_types"):
                for obj_ in obj._trait.trait_types:
                    yield from TypedInstanceTuple._all_traits(obj_)
            else:
                yield obj._trait
        if isinstance(obj, TraitType):
            yield obj

    def __init__(self, trait: TraitType[T, T], *, allow_none=False, read_only=False, help=""):  # noqa: A002
        """A tuple style trait where elements can be spawned and observed with ValueTraits.on_change."""
        if not isinstance(trait, TraitType):
            msg = f"{trait=} is not a TraitType"
            raise TypeError(msg)
        self._trait = trait
        super().__init__(allow_none=allow_none, read_only=read_only, help=help)
        self._close_observers = weakref.WeakKeyDictionary()

    def class_init(self, cls: type[Any], name: str | None) -> None:
        super().class_init(cls, name)
        self._trait.class_init(cls, None)

    def subclass_init(self, cls: type[ValueTraits]):  # type: ignore
        if not issubclass(cls, ValueTraits):
            msg = "TypedInstanceTuple is only compatible with ValueTraits or a subclass."
            raise TypeError(msg)
        super().subclass_init(cls)
        # Required to ensure instance_init is always called during init
        if hasattr(cls, "_instance_inits") and self.instance_init not in cls._instance_inits:
            cls._instance_inits.append(self.instance_init)

    def instance_init(self, obj: ValueTraits):
        """Init an instance of TypedInstanceTuple."""
        self._trait.instance_init(obj)
        super().instance_init(obj)
        utils.weak_observe(
            obj,
            obj._vt_tuple_on_change,
            names=self.name,
            tuplename=self.name,
            on_add=self._get_func(obj, "_on_add"),
            on_remove=self._get_func(obj, "_on_remove"),
            _tuple_on_add=self._tuple_on_add,
            _tuple_on_remove=self._tuple_on_remove,
            pass_change=True,
        )  # type: ignore

    def validate(self, obj: ValueTraits, value: ProposalType):
        if obj.closed:
            return ()
        try:
            if self.validating:
                return getattr(obj, self.name) if obj.trait_has_value(self.name) else self.default()
            with self._busy_validating():
                values = []
                for i, v in enumerate(value):
                    val = v
                    try:
                        self._trait._validate(obj, val)
                    except Exception as e:
                        if isinstance(val, dict):
                            val = self.new_update_inst(obj, val, i)
                        else:
                            e.add_note(f"`{obj.__class__.__name__}.{self.name}` {obj=}")
                            raise
                    if val is None:
                        continue
                    if id(val) not in map(id, values) and not getattr(val, "closed", False):
                        values.append(val)
                return tuple(values)
        except Exception as e:
            obj.on_error(e, "Trait validation error", self)
            raise

    def new_update_inst(self, obj, kw: dict, index=None):
        if inst := self._find_update_item(obj, kw, index=index):
            return inst
        if not self._spawn_new_instances:
            msg = f"Instance creation is disabled for items in the TypedInstanceTuple {utils.fullname(self.this_class)}.{self.name}"
            raise RuntimeError(msg)
        factory = self._get_func(obj, "_factory")
        if not callable(factory):
            factory = getattr(self._trait, "klass", None)
        if not factory:
            msg = f"A factory is required for {utils.fullname(obj)}.{self.name}"
            raise RuntimeError(msg)
        try:
            if self._set_parent:
                kw = {"parent": obj} | kw
            return factory(**kw)
        except Exception as e:
            if mb.DEBUG_ENABLED:
                raise
            msg = (
                f"Unable to create new instance of {self._trait}"
                f" factory={utils.fullname(obj)}.{self._factory}\n"
                f"kw={utils.limited_string(kw, 60)}"
            )
            raise ValueError(msg) from e

    def _find_update_item(self, obj, kw: dict, index: int | None):
        """Check if an item exists in current tuple matching update_by in kw.

        The first inst found is updated with kw and returned.
        """
        ub = self._update_by
        if ub is None:
            return None
        if ub is defaults.INDEX:
            if index is None:
                return None
        elif ub not in kw:
            return None
        current = getattr(obj, self.name)
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

    def _get_func(self, obj: ValueTraits, attr: str) -> Callable | None:
        """Get a function defined in the mapping by from metadata.

        These can be set by .tag()
        """
        if mb.DEBUG_ENABLED and attr not in self._callback_specs:
            msg = f"{attr} has not been mapped to a function for {obj.__class__}"
            raise KeyError(msg)
        funcname = getattr(self, attr)
        if not funcname:
            return None
        func = getattr(obj, funcname, None)
        if func is None:
            msg = f'The callback "{utils.fullname(obj)}.{funcname}" is not defined!'
            raise AttributeError(msg)
        if not callable(func):
            msg = f"{utils.fullname(obj)}.{funcname} is not callable!"
            raise TypeError(msg)
        sig = inspect.signature(func)
        if set(self._callback_specs[attr]).difference(sig.parameters):
            msg = f"{func} is missing the following named arguments: {list(self._callback_specs[attr])})"
            raise AttributeError(msg)
        return func

    def configure(
        self,
        *,
        update_by="name",
        update_item_names: tuple[str, ...] | str = (),
        spawn_new_instances: bool = True,
        set_parent=True,
        close_on_remove=True,
        factory="",
        on_add="",
        on_remove="",
    ) -> Self:
        """Change the behaviour of the typed instance tuple.

        Parameters
        ----------
        update_by: str
            If an existing instance with attribute name corresponding to a passed dict,
            it will be updated rather than spawning a new instance.
        update_item_names:
            The names of traits of each instance to observe for a change. Changes are
            passed to `on_change` of the ValueTraits object.
        spawn_new_instances: bool
            If set False, it will not attempt to create a new instance when a
             dict is passed. Thus factory will not be used, updating values
             is still permitted.
        set_parent: bool
            Set the parent of the trait items to the value_traits instance to which this
            tuple belongs.
            *note:* parent is passed as a kwarg during instantiation of new objects.
        close_on_remove: bool
            close the instance once it is removed

        factory (**kwargs): str
            The name of a method of the object to which the tuple belongs.
            It must return an instance of the specified trait.

        on_add(obj) : str
            The name of a method called when a new object is added to the tuple.
            Each new object is passed.

        on_remove(obj): st | None
            on_add and on_remove are called on each element that is added / removed
            existing items not called)
            signature : on_add(obj)


        expected convention:
            * method (self, change or obj)
            * class method

        """
        self._update_by = update_by if update_by is defaults.INDEX else str(update_by)
        self._update_item_names = tuple(utils.iterflatten(update_item_names))
        self._spawn_new_instances = bool(spawn_new_instances)
        if self._spawn_new_instances and not factory and not getattr(self._trait, "klass", None):
            msg = "A factory is required when trait doesn't specify a klass (such as Union)"
            raise RuntimeError(msg)
        self._set_parent = bool(set_parent)
        self._close_on_remove = bool(close_on_remove)
        self._on_add = on_add
        self._on_remove = on_remove
        self._factory = factory
        return self

    def _tuple_on_add(self, parent: ValueTraits, obj: HasParent):
        if isinstance(obj, HasParent) and self._set_parent:
            obj.parent = parent
        if isinstance(obj, HasParent | Widget) and obj not in self._close_observers:
            names = "closed" if isinstance(obj, HasParent) else "comm"
            handle = utils.weak_observe(obj, self._observe_obj_closed, names, False, weakref.ref(parent), names)
            self._close_observers[obj] = handle, names

    def _tuple_on_remove(self, _: ValueTraits, obj: HasParent):
        if isinstance(obj, HasParent | Widget) and (args := self._close_observers.pop(obj, None)):
            obj.unobserve(*args)
        if self._close_on_remove and hasattr(obj, "close"):
            obj.close()

    def tag(self, **kw):
        raise NotImplementedError

    def _observe_obj_closed(self, ref: weakref.ref[ValueTraits], name: str):
        if (parent := ref()) and not parent.closed:
            filt = (lambda obj: not obj.closed) if name == "closed" else lambda obj: obj.comm
            values = filter(filt, getattr(parent, self.name))
            parent.set_trait(self.name, values)


class _TypedTupleRegister(HasParent):
    """A simple register to track observer,name pairs."""

    if TYPE_CHECKING:
        parent: ValueTraits
    reg: set[tuple[HasTraits, str]] = Set()  # type: ignore

    @observe("reg")
    def _observe_reg(self, change: ChangeType):
        self.parent._vt_observe_vt_reg_value(change)

    def change_handler(self, change: ChangeType):
        """"""
        if self.parent:
            self.parent._vt_on_reg_tuples_change(change, self.name)
        else:
            pass


class CallbackMode(enum.Enum):
    external = enum.auto()
    internal = enum.auto()


INTERNAL = CallbackMode.internal
EXTERNAL = CallbackMode.external


class ValueTraits(HasParent, Generic[R]):
    """ValueTraits is a class that provides a way to manage and observe changes to
    a collection of traits, particularly those that represent values or settings.

    It extends HasParent and incorporates features for handling nested traits,
    typed instance tuples, and change notifications.
    Key Features:
    - Value Trait Management: Allows defining and observing changes to a set of
        value traits, specified by dotted names (e.g., "a.b.c").  Changes to these
        traits trigger the `on_change` method.
    - Persistence: Supports a separate set of value traits that are persisted
        (e.g., saved to a file).
    - Typed Instance Tuples: Integrates with TypedInstanceTuple to manage
        collections of objects with specific types and observe changes within those
        collections.
    - Change Notifications: Provides a mechanism for handling change events,
        including the ability to temporarily ignore changes and to propagate
        changes to parent objects.
    - Initialization: Ensures proper initialization of the object, including
        setting up the home directory, parent object, and initial values.
    - Data Loading and Conversion: Supports loading values from dictionaries,
        YAML strings, and callables, and converting the object's state to
        dictionaries, JSON, and YAML.
    - Error Handling: Includes error handling for invalid trait names, data
        loading errors, and change event errors.
    - Utilities: Offers utility methods for getting and setting values,
        converting the object to a dictionary, and generating JSON and YAML
        representations.
    The class uses traitlets for defining and observing traits, and it
    incorporates features for handling nested traits, typed instance tuples,
    and change notifications. It also provides a way to load values from
    dictionaries, YAML strings, and callables, and to convert the object's
    state to dictionaries, JSON, and YAML.
    """

    _STASH_DEFAULTS = False
    _AUTO_VALUE = True  # Also connects the trait 'value' on the trait if it is found.
    _ignore_change_cnt = 0
    _vt_reg_value_traits_persist: set[tuple[HasTraits, str]] = Set()  # type: ignore
    _vt_reg_value_traits: set[tuple[HasTraits, str]] = Set()  # type: ignore
    _vt_tuple_reg: Dict[str, _TypedTupleRegister] = Dict(read_only=True)
    _vt_tit_names: ClassVar[dict] = {}
    _vt_busy_updating_count = 0
    _vt_init_complete = False
    dtype = "dict"
    home = InstanceHome()
    value = _ValueTraitsValueTrait()
    value_traits = NameTuple()
    value_traits_persist = NameTuple()
    _prohibited_parent_links: ClassVar[set[str]] = {"home"}
    _prohibited_value_traits: ClassVar[set[str]] = {"parent"}
    if TYPE_CHECKING:
        _value: Callable

    @contextlib.contextmanager
    def ignore_change(self):
        """Context manager to temporarily ignore changes.

        Increments the ignore change counter before entering the context and
        decrements it after leaving the context. This is useful when you want
        to temporarily disable change notifications in `on_change`.
        """

        self._ignore_change_cnt = self._ignore_change_cnt + 1
        try:
            yield
        finally:
            self._ignore_change_cnt = self._ignore_change_cnt - 1

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        if self.closed:
            return super().__repr__()
        cs = "closed: " if self.closed else ""
        home = f"home:{self.home}" if self._vt_init_complete else ""
        return f"<{cs}{self.__class__.__qualname__} name='{self.name}' {home}>"

    def __init_subclass__(cls, **kwargs) -> None:
        tn_ = dict(cls._vt_tit_names)
        for c in cls.mro():
            if c is __class__:
                break
            if issubclass(c, ValueTraits) and c._vt_tit_names:
                # Need to copy across other unregistered TypedInstanceTuple mappings
                for name in c._vt_tit_names:
                    if name not in tn_:
                        tn_[name] = c._vt_tit_names[name]
            if c is HasTraits:
                msg = (
                    "This class has invalid MRO please ensure ValueTraits is higher "
                    "up the MRO. This can be done by changing the inheritance order"
                    "in the class definition."
                )
                raise RuntimeError(msg)
        cls._vt_tit_names = tn_
        super().__init_subclass__(**kwargs)

    def _init_CHECK_PARENT(self):
        if self.parent:
            msg = "Parent must not be set prior to init of ValueTraits."
            raise RuntimeError(msg)

    def __new__(cls, *, home: Home | str | None = None, parent: HasParent | None = None, **kwargs) -> Self:
        if home:
            home = Home(home)
        elif isinstance(parent, ValueTraits):
            home = parent.home
        elif isinstance(parent, Home):
            home = parent
        else:
            msg = "'home' or 'parent' (with a home) must be provided. 'home' may be a string."
            raise NameError(msg)
        inst = super().__new__(cls, home=home, parent=parent, **kwargs)
        if not inst._vt_init_complete and home and inst.has_trait("home"):  # type: ignore
            inst.set_trait("home", home)
        return inst

    def __init__(
        self,
        *,
        home: Home | str | None = None,
        parent: R = None,
        value_traits: Collection[str] | None = None,
        value_traits_persist: Collection[str] | None = None,
        value: dict | Callable[[], dict] | None | str = None,
        **kwargs,
    ):
        """Initializes the ValueTraits object.

        Args:
            home (Home | str | None, optional): The home directory. Defaults to None.
            parent (HasParent | None, optional): The parent object. Defaults to None.
            value_traits (Collection[str] | None, optional): A collection of value trait names. Defaults to None.
            value_traits_persist (Collection[str] | None, optional): A collection of value trait names that persist. Defaults to None.
            value (dict | Callable[[], dict] | None | str, optional): The initial value, which can be a dictionary, a callable that returns a dictionary, a YAML string, or None (defaults to an empty dictionary).
            **kwargs: Additional keyword arguments.
        """

        value = {} if value is None else value
        if self._vt_init_complete:
            return
        if hasattr(self, "vt_validating"):
            msg = (
                f"{utils.fullname(__class__)}__ini__ BUG. If there are items\n"
                f" in {self.SINGLETON_BY=} check for bugs in the init of the object.\n"
                "Otherwise check which validation is occurring before init is complete."
            )
            raise RuntimeError(msg)
        self._init_CHECK_PARENT()
        self.vt_validating = False
        self.vt_updating = False
        self.set_trait("value_traits", value_traits or self.value_traits)
        self.set_trait("value_traits_persist", value_traits_persist or self.value_traits_persist)
        vts = []
        for v in (*self.value_traits_persist, *self.value_traits, *self._vt_tit_names):
            if v not in vts:
                vts.append(v)
        if callable(value):
            value = value()
        if isinstance(value, str):
            value = ruamel.yaml.YAML(typ="safe").load(value)
        if not isinstance(value, dict):
            msg = "Expected a dict"
            raise TypeError(msg)
        value = dict(value)
        # Extract kwargs that overlap with value_traits/persist in order or vts
        for n in vts:
            name = n
            if name in kwargs:
                value[name] = kwargs.pop(name)
            elif not name.endswith(".value"):
                # Also handle .value in case it is set explicitly
                name = name + ".value"
                if name in kwargs:
                    value[name] = kwargs.pop(name)
        for k in list(kwargs):
            if "." in k:
                value[k] = kwargs.pop(k)
        self._init_CHECK_PARENT()
        self._init_tuple_reg()
        self._vt_update_reg_value_traits()
        self._vt_update_reg_value_traits_persist()
        self.observe(self._vt_value_traits_observe, names=("value_traits", "value_traits_persist"))
        self._vt_init_complete = True
        super().__init__(parent=parent, **kwargs)
        # Parent must be set prior to setting value because HasParent
        # may load data from a parent which is need to load values
        if self._STASH_DEFAULTS:
            self._DEFAULTS = self.to_dict()
        if value:
            self.set_trait("value", value)

    @observe("closed")
    def _vt_observe_closed(self, change: ChangeType):
        # Unobserve by clearing the registers
        self._ignore_change_cnt = self._ignore_change_cnt + 1
        self._vt_tuple_reg.clear()
        self._vt_reg_value_traits = set()
        self._vt_reg_value_traits_persist = set()

    def _init_tuple_reg(self):
        """Create registers TypedInstanceTuples."""

        for name in self._vt_tit_names:
            self._vt_tuple_reg[name] = _TypedTupleRegister(name=name, parent=self)
            self._vt_update_reg_tuples(name)

    def tag(self, **kw):
        msg = f"The metadata passed be use {list(kw)}"
        raise NotImplementedError(msg)

    @observe("_vt_reg_value_traits", "_vt_reg_value_traits_persist")
    def _vt_observe_vt_reg_value(self, change: ChangeType):
        """Reacts to changes in the registered value traits.

        This method observes changes in the `_vt_reg_value_traits` and
        `_vt_reg_value_traits_persist` attributes, as well as changes originating
        from a `_TypedTupleRegister`. It then appropriately observes or unobserves
        the relevant objects based on the changes.
        Args:
            change (ChangeType): A dictionary describing the change that occurred.
                It should contain keys like 'name' (the name of the attribute that
                changed), 'old' (the old value of the attribute), 'new' (the new
                value of the attribute), and 'owner' (the object that owns the
                attribute).
        Raises:
            NotImplementedError: If the change event does not originate from
                `_vt_reg_value_traits`, `_vt_reg_value_traits_persist`, or a
                `_TypedTupleRegister`.
        """
        if change["name"] == "_vt_reg_value_traits":
            handler = self._vt_on_reg_value_traits_change
        elif change["name"] == "_vt_reg_value_traits_persist":
            handler = self._vt_on_value_traits_persist_change
        elif isinstance(change["owner"], _TypedTupleRegister):
            handler = change["owner"].change_handler
        else:
            msg = f"{change['name']}"
            raise NotImplementedError(msg)
        old = set() if change["old"] is Undefined else change["old"]
        new = change["new"]
        for obj, name in old.difference(new):
            with contextlib.suppress(Exception):
                obj.unobserve(handler, name)
        for obj, name in new.difference(old):
            obj.observe(handler, names=name)

    @classmethod
    def _get_observer_pairs(cls, obj: HasTraits, dotname: str) -> Iterator[tuple[HasTraits, str]]:
        """Generates pairs of (object, trait_name) for observing a dotted trait name.

        This method traverses a dotted trait name, yielding tuples of (object, trait_name)
        for each trait encountered along the path. It handles special cases like the
        'value' trait and ignores first-level-non-traits assuming they will not be changed.

        Args:
            cls: The class that this method is bound to (used for accessing class-level attributes like _AUTO_VALUE).
            obj: The starting HasTraits object.
            dotname: The dotted trait name to observe (e.g., "a.b.c").

        Yields:
            tuple[HasTraits, str]: Pairs of (object, trait_name) to observe.  The object is a
            HasTraits instance, and the trait_name is a string representing the name of a trait
            on that object.

        Raises:
            TypeError: If a non-trait attribute is encountered in the dotname (except for the
            first level) or if the attribute is not a HasTraits instance.
            AttributeError: If an attribute in the dotname does not exist and the object is not a Bunched instance.
        """
        parts = dotname.split(".")
        segments = len(parts)
        try:
            for i, n in enumerate(parts, 1):
                if n in obj._traits:
                    yield (obj, n)
                elif (obj_ := getattr(obj, n, None)) and isinstance(obj_, HasTraits):
                    # We tolerate non-traits in a HasTraits object assuming they are 'fixed' for the life of object in which they reside.
                    obj = obj_
                    if cls._AUTO_VALUE and i == segments and obj.has_trait("value"):
                        yield (obj, "value")
                    continue
                else:
                    msg = (
                        f"`{n}` is not a trait of {utils.fullname(obj)} and {utils.fullname(obj)} "
                        f"is not an instance of HasTraits so is an invalid part of {dotname}."
                    )
                    raise TypeError(msg)
                if n in obj._trait_values:
                    obj = obj._trait_values[n]
                elif n in getattr(obj, "_InstanceHP", {}):
                    break
                else:
                    try:
                        # obj is not an instance of HasParent and/or n is not an InstanceHP trait
                        obj = getattr(obj, n)
                    except TraitError:
                        # No default - so okay to break
                        break
                if obj is None:
                    break
                if cls._AUTO_VALUE and i == segments and n != "value" and "value" in getattr(obj, "_traits", {}):
                    yield (obj, "value")
        except AttributeError:
            if not isinstance(obj, Bunched):
                raise

    @classmethod
    def _get_new_update_inst(cls, tuplename: str) -> Callable[[ValueTraits, dict, int | None], Any]:
        """Return the constructor to create a new item that belongs to a typed instance tuple.

        Args:
            tuplename: Name of the typed instance tuple.

        Raises:
            KeyError: If the tuple name is not registered.

        Returns:
            Constructor for the typed instance tuple.
        """
        if tuplename not in cls._vt_tit_names:
            msg = (
                f"{tuplename=} is not a registered typed_instance_tuple "
                f"Register tuple names ={list(cls._vt_tit_names)}!"
            )
            raise KeyError(msg)
        return cls._vt_tit_names[tuplename]["new_update_inst"]

    def _vt_update_reg_value_traits(self):
        pairs = set()
        if not self.closed:
            for dotname in self.value_traits:
                for pair in self._get_observer_pairs(self, dotname):
                    pairs.add(pair)
            self._vt_reg_value_traits = pairs

    def _vt_update_reg_value_traits_persist(self):
        pairs = set()
        if not self.closed:
            for dotname in self.value_traits_persist:
                for pair in self._get_observer_pairs(self, dotname):
                    pairs.add(pair)
            self._vt_reg_value_traits_persist = pairs

    def _vt_update_reg_tuples(self, tuplename):
        names = self._vt_tit_names[tuplename]["update_item_names"]
        items = getattr(self, tuplename)
        pairs = set()
        for obj in items:
            for dotname in names:
                for owner, n in self._get_observer_pairs(obj, dotname):
                    pairs.add((owner, n))
        self._vt_tuple_reg[tuplename].reg = pairs

    def _vt_value_traits_observe(self, change: ChangeType):
        if mb.DEBUG_ENABLED and self._prohibited_value_traits.intersection(change["new"]):
            msg = f"A prohibited value trait has been detected: {self._prohibited_value_traits.intersection(change['new'])}"
            raise RuntimeError(msg)
        if change["name"] == "value_traits":
            try:
                self._vt_update_reg_value_traits()
            except Exception as e:
                e.add_note(f"This is a `value_trait` of {self!r}")
                self.on_error(e, "Invalid `value_trait` item found.")
                if mb.DEBUG_ENABLED:
                    raise
        if change["name"] == "value_traits_persist":
            try:
                self._vt_update_reg_value_traits_persist()
            except Exception as e:
                e.add_note(f"This is a `value_trait_persist` of {self!r}")
                self.on_error(e, "Invalid `value_trait_persist` item found.")
                if mb.DEBUG_ENABLED:
                    raise

    def _vt_tuple_on_change(
        self,
        change: ChangeType,
        tuplename: str,
        on_add: Callable | None,
        on_remove: Callable | None,
        _tuple_on_add: Callable,
        _tuple_on_remove: Callable,
    ):
        """Handles changes to tuples within ValueTraits, triggering callbacks.

        This method is called when a tuple (`TypedInstanceTuple`) associated with a ValueTraits instance
        is modified (elements added or removed). It identifies the changes,
        executes registered callbacks, and propagates the change notification.

        Args:
            change: A dictionary describing the change event, including the
                'new' and 'old' values, and the 'owner' (ValueTraits instance).
            tuplename: The name of the tuple that was changed.
            on_add: An optional callback function to be executed when elements
                are added to the tuple.  This is considered an EXTERNAL callback.
            on_remove: An optional callback function to be executed when elements
                are removed from the tuple. This is considered an EXTERNAL callback.
            _tuple_on_add: An optional callback function to be executed when elements
                are added to the tuple. This is considered an INTERNAL callback.
            _tuple_on_remove: An optional callback function to be executed when elements
                are removed from the tuple. This is considered an INTERNAL callback.
        """
        # Collect pairs and update register
        if self.closed:
            return
        self._vt_update_reg_tuples(tuplename)
        # Callbacks
        new = set(change["new"])
        old = set(change["old"] or ())
        obj: ValueTraits = change["owner"]  # type: ignore
        if _tuple_on_remove or on_remove:
            for val in old.difference(new):
                if _tuple_on_remove:
                    self._typed_tuple_do_callback(_tuple_on_remove, obj, val, tuplename, INTERNAL)
                if on_remove:
                    self._typed_tuple_do_callback(on_remove, obj, val, tuplename, EXTERNAL)
        if _tuple_on_add or on_add:
            for val in new.difference(old):
                if _tuple_on_add:
                    self._typed_tuple_do_callback(_tuple_on_add, obj, val, tuplename, INTERNAL)
                if on_add:
                    self._typed_tuple_do_callback(on_add, obj, val, tuplename, EXTERNAL)
        # Share notification to on_change and update the value
        if change["name"] not in (*self.value_traits, *self.value_traits_persist):
            self._vt_on_change(change)

    def _typed_tuple_do_callback(
        self, callback: Callable, obj: ValueTraits, val: Any, tuplename: str, mode: CallbackMode
    ):
        """Callback specific to typed instance tuples. for on_change, on_add, on_remove.

        Will log an error on failure rather than raising it (except when debugging)
        """
        try:
            callback(self, val) if mode is INTERNAL else callback(val)
        except Exception as e:
            obj.on_error(e, f"Typed tuple callback '{tuplename}'")
            if mb.DEBUG_ENABLED:
                raise

    def _vt_on_reg_value_traits_change(self, change: ChangeType):
        if (isinstance(change["new"], HasTraits) or isinstance(change["old"], HasTraits)) and (
            change["new"] is not change["old"]
        ):
            self._vt_update_reg_value_traits()
        self._vt_on_change(change)

    def _vt_on_value_traits_persist_change(self, change: ChangeType):
        if (isinstance(change["new"], HasTraits) or isinstance(change["old"], HasTraits)) and (
            change["new"] is not change["old"]
        ):
            self._vt_update_reg_value_traits_persist()
        self._vt_on_change(change)

    def _vt_on_reg_tuples_change(self, change, traitname):
        if (isinstance(change["new"], HasTraits) or isinstance(change["old"], HasTraits)) and (
            change["new"] is not change["old"]
        ):
            self._vt_update_reg_tuples(traitname)
        self._vt_on_change(change)

    def _vt_on_change(self, change: ChangeType):
        """Handles changes to the observed trait values.

        This method is called when a change occurs in one of the observed traits.
        It updates the internal state, calls the user-defined `on_change` method,
        and handles any exceptions that occur during the change event.  It also
        manages a counter to prevent re-entrant calls to `on_change` and resets
        the trait value after the update is complete.

        Args:
            change (ChangeType): A traitlets *change*.
        """
        if mb.DEBUG_ENABLED:
            self.log.debug(
                f"  CHANGE: [{change['owner'].__class__.__qualname__}.{change['name']}] "
                f"{utils.limited_string(repr(change['old']))} ➮ {utils.limited_string(repr(change['new']))}  "
                f"{f'ignored (context={self._ignore_change_cnt})' if self._ignore_change_cnt else ''}"
            )
        if self._ignore_change_cnt:
            return
        # `value` updated after "leaving context" (originally using context but only used here.)
        self.vt_updating = True
        self._vt_busy_updating_count = self._vt_busy_updating_count + 1
        try:
            self.on_change(change)
        except Exception as e:
            if self._vt_busy_updating_count == 1:
                self.on_error(e, "Change event error", change)
            raise
        finally:
            self._vt_busy_updating_count -= 1
            if not self._vt_busy_updating_count:
                self.vt_updating = False
                if self._vt_init_complete and not self.vt_validating:
                    self.set_trait("value", defaults.NO_VALUE)

    def _load_value(self, data: Literal[defaults._NoValue.token] | dict | Callable):
        if self.closed:
            return
        try:
            self.load_value(data)
        except Exception as e:
            self.on_error(e, "Error loading data", data)
            raise

    @property
    @override
    def repr_log(self):
        if self.closed:
            return super().repr_log
        name = self.name
        name = f" {name=}" if name else ""
        return f"<{self.__class__.__name__}{name}> [{self.home}]"

    def add_value_traits(self, *names: str, delay: float | None = None):
        """Append names to value_traits.

        delay: if it is not None, it will be called with a delay.
            a delay = 0 is equivalent to `asyncio.call_soon`.
        """
        if delay is not None:
            mb_async.call_later(0, self.add_value_traits, *names)
            return
        self.set_trait("value_traits", (*self.value_traits, *names))

    def drop_value_traits(self, *names: str):
        """Remove to value_traits.

        value_traits are used for notifications. Dotted paths are permitted.
        """
        self.set_trait("value_traits", (v for v in self.value_traits if v not in names))

    def load_value(self, data: Literal[defaults._NoValue.token] | dict | Callable[[], dict] | pathlib.Path | str):
        if data is not defaults.NO_VALUE and data:
            while callable(data):
                data = data()
            if isinstance(data, str | pathlib.Path):
                data = ruamel.yaml.YAML(typ="safe").load(data)
            if not isinstance(data, dict):
                msg = f"Expected a dict but got a {data.__class__}."
                raise TypeError(msg)

            utils.load_nested_attrs(self, data, raise_errors=False, default_setter=self.setter, on_error=self.on_error)

    def get_value(self, dotname: str, default=None) -> Any:
        """Gets value by dotted name.

        If dottedname points to a HasTraits object with a value, the value will be
        returned. Uses utils.getattr_nested.

        (Callables will be evaluated).
        """
        return utils.getattr_nested(self, dotname, default=default)

    @staticmethod
    def getattr(obj, name, default=defaults.NO_VALUE):
        """Like getattr but will test and call if callable (recursively)."""
        val = getattr(obj, name, default) if not defaults.is_no_value(default) else getattr(obj, name)
        while callable(val):
            val = val()
        return val

    def to_dict(self, names: None | Iterable[str] = None, hastrait_value=True) -> dict[str, Any]:
        """Converts the object's value traits to a dictionary.

        Args:
            names: An optional iterable of attribute names to include in the dictionary.
            If None, the attributes in `self.value_traits_persist` are used.
            hastrait_value: If True, only include attributes that have a trait value.

        Returns:
            A dictionary where keys are attribute names and values are the corresponding
            attribute values.
        """
        if self.closed:
            self.log.warning("This object is closed")
            return {}
        if names is None:
            names = self.value_traits_persist
        return {n: utils.getattr_nested(self, n, hastrait_value=hastrait_value) for n in names}

    _value = to_dict  # Alias provided to allow for easy overloading

    if TYPE_CHECKING:

        @overload
        def to_json(self) -> str: ...
        @overload
        def to_json(self, names: None | Iterable[str]) -> str: ...
        @overload
        def to_json(self, names: None | Iterable[str], option: int) -> str: ...
        @overload
        def to_json(self, names: None | Iterable[str], option: int, decode: Literal[False]) -> bytes: ...

    def to_json(
        self,
        names: None | Iterable[str] = None,
        option: int = orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_INDENT_2,
        decode=True,
    ) -> str | bytes:
        """Convert the object to a JSON string.

        Args:
            names (Optional[Iterable[str]]): An optional list of dottednames to include in the JSON instead of thosed listed in the property `value_traits_persist`.
            option (int): orjson options.
            decode (bool): If True, decode the JSON string to a string. Defaults to True.

        Returns:
            str | bytes: A JSON string representation of the object.
        """
        try:
            data = self.to_dict(names, hastrait_value=True)
        except TypeError:
            data = self.to_dict()
            if names:
                self.log.warning(f"Ignored {names=}", stack_info=True)
        try:
            data = orjson.dumps(data, default=json_default_converter, option=option)
            if decode:
                return data.decode()
        except TypeError:
            raise
        except Exception:
            return json.dumps(data, default=json_default_converter)
        else:
            return data

    def to_yaml(
        self, names: None | Iterable[str] = (), fs: AbstractFileSystem | None = None, path: str | None = None
    ) -> str:
        """Convert settings to yaml.
        Args:
            names (Optional[Iterable[str]]): An optional list of dottednames to include in the JSON instead of thosed listed in `value_traits_persist`.
            fs: fsspec filesystem
            path: When fs and path are provided the yaml is written to the file in the fs at path.
        """
        return to_yaml(self.to_dict(names=names), walkstring=True, path=path, fs=fs)  # type: ignore

    def on_change(self, change: ChangeType):
        """Handle change events of all traits listed in `value_traits` and `value_trait_persist`.

        Since nested traits are allowed, trait changes in children are also observed.
        adding, removing and creating (InstanceHP only) of items are all propagated.

        `TypedInstanceTuples` change events are also delivered here, specify the
        `update_item_names` with the `configure` method when defining them in a class,
        dynamically changing this is not currently supported.

        To overload, included a call to super(), passing or intercepting changes as
        appropriate.

        Use the context method `ignore_change` to set a value and ignore the change
        in `on_change` only (the trait change is still triggered).

        ``` python
        def on_change(self, change: mb.ChangeType):
            super().on_change(change)
            ...
        ```

        Using super().on_change() should be avoided. Instead call directly the methods
        as required.
        """

        on_change = getattr(super(), "on_change", None)
        if callable(on_change):
            on_change(change)

    def get_tuple_obj(self, tuplename: str, add=True, **kwds):
        """Retrieves or creates an object associated with a `TypedInstaneTuple` tuple trait.

        This method retrieves an existing object associated with a tuple trait
        or creates a new one if it doesn't exist. It also adds the new object
        to the tuple trait if specified.

        Args:
            tuplename (str): The name of the tuple trait.
            add (bool, optional): Whether to add the new object to the tuple.
            Defaults to True.
            **kwds: Keyword arguments to pass to the object's constructor.
            Can include 'index' to specify the index of the object.

        Returns:
            The object associated with the `TypedInstaneTuple` tuple trait.
        """
        new_update_inst = self._get_new_update_inst(tuplename)
        index = kwds.pop("index", None)
        obj = new_update_inst(self, kwds, index)
        if add:
            t = getattr(self, tuplename)  # type:tuple
            if obj not in t:
                self.set_trait(tuplename, (*t, obj))
        return obj
