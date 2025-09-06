from __future__ import annotations

import contextlib
import json
import pathlib
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self, cast, overload

import orjson
import ruamel.yaml
from traitlets import HasTraits, TraitError, TraitType, Undefined, observe

import menubox as mb
from menubox import defaults, mb_async, utils
from menubox.hasparent import HasParent
from menubox.pack import json_default, to_yaml
from menubox.trait_factory import TF
from menubox.trait_types import RP, Bunched, ChangeType, NameTuple, ReadOnly

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Iterator

    from fsspec import AbstractFileSystem

    from menubox.instancehp_tuple import InstanceHPTuple


__all__ = ["ValueTraits"]


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
        obj._notify_trait(self.name, obj.json_default, new_value)

    def _validate(self, obj: ValueTraits, value):
        if obj.vt_validating:
            msg = "Validation in progress!"
            raise RuntimeError(msg)
        obj.vt_validating = True
        try:
            obj._load_value(value)
            return obj.json_default
        finally:
            obj.vt_validating = False


class _InstanceHPTupleRegister(HasParent):
    """A simple register to track observer,name pairs."""

    parent = TF.parent(klass=cast("type[ValueTraits]", "menubox.valuetraits.ValueTraits"))
    reg: TF.InstanceHP[Self, set[tuple[HasTraits, str]], ReadOnly[set]] = TF.Set().configure(TF.IHPMode.XLR_)

    @observe("reg")
    def _observe_reg(self, change: ChangeType):
        if parent := self.parent:
            parent._vt_observe_vt_reg_value(change)

    def change_handler(self, change: ChangeType):
        """"""
        if parent := self.parent:
            parent._vt_on_reg_tuples_change(change, self.name)
        else:
            pass


class ValueTraits(HasParent):
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
    - Typed Instance Tuples: Integrates with InstanceHPTuple to manage
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
    _vt_reg_value_traits_persist = TF.Set()
    _vt_reg_value_traits = TF.Set()
    _vt_tuple_reg = TF.DictReadOnly(co_=cast(Self, 0), klass_=cast("type[dict[str, _InstanceHPTupleRegister]]", 0))
    _InstanceHPTuple: ClassVar[dict[str, InstanceHPTuple]] = ()  # type: ignore # We use empty tuple to provide iterable
    _vt_busy_updating_count = 0
    _vt_init_complete = False
    dtype = "dict"
    value = _ValueTraitsValueTrait()
    value_traits = NameTuple()
    value_traits_persist = NameTuple()
    PROHIBITED_PARENT_LINKS: ClassVar[set[str]] = {"home"}
    _prohibited_value_traits: ClassVar[set[str]] = {"parent"}

    if TYPE_CHECKING:
        json_default: Callable

    @contextlib.contextmanager
    def ignore_change(self):
        """Context manager to temporarily ignore changes.

        Whilst in this context all changes register with 'value_traits' and 'value_traits_persist'
        will not be passed to `on_change` and 'value' change will not be emitted immediately.
        """

        self._ignore_change_cnt = self._ignore_change_cnt + 1
        try:
            yield
        finally:
            self._ignore_change_cnt = self._ignore_change_cnt - 1

    def __str__(self):
        return self.__repr__()

    def __init_subclass__(cls, **kwargs) -> None:
        tn_ = dict(cls._InstanceHPTuple or {})
        for c in cls.mro():
            if c is __class__:
                break
            if issubclass(c, ValueTraits) and c._InstanceHPTuple:
                # Need to copy across other unregistered InstanceHPTuple mappings
                for name in c._InstanceHPTuple:
                    if name not in tn_:
                        tn_[name] = c._InstanceHPTuple[name]
            if c is HasTraits:
                msg = (
                    "This class has invalid MRO please ensure ValueTraits is higher "
                    "up the MRO. This can be done by changing the inheritance order"
                    "in the class definition."
                )
                raise RuntimeError(msg)
        cls._InstanceHPTuple = tn_
        super().__init_subclass__(**kwargs)

    def __init__(
        self,
        *,
        parent: RP = None,  # type: ignore
        value_traits: Collection[str] | None = None,
        value_traits_persist: Collection[str] | None = None,
        value: dict | Callable[[], dict] | None | str | bytes = None,
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
                f" in {self.SINGLE_BY=} check for bugs in the init of the object.\n"
                "Otherwise check which validation is occurring before init is complete."
            )
            raise RuntimeError(msg)
        self.vt_validating = False
        self.vt_updating = False
        self.set_trait("value_traits", value_traits or self.value_traits)
        self.set_trait("value_traits_persist", value_traits_persist or self.value_traits_persist)
        vts = []
        for v in (*self.value_traits_persist, *self.value_traits, *self._InstanceHPTuple):
            if v not in vts:
                vts.append(v)
        value = mb.pack.to_dict(value)
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
        self._vt_update_reg_value_traits()
        self._vt_update_reg_value_traits_persist()
        self.observe(self._vt_value_traits_observe, names=("value_traits", "value_traits_persist"))
        self._vt_init_complete = True
        super().__init__(parent=parent, **kwargs)
        self.set_trait("value", value)
        if self._STASH_DEFAULTS:
            self._DEFAULTS = self.to_yaml()

    @observe("closed")
    def _vt_observe_closed(self, change: ChangeType):
        # Unobserve by clearing the registers
        self._ignore_change_cnt = self._ignore_change_cnt + 1
        for reg in self._vt_tuple_reg.values():
            reg.close()
        self._vt_tuple_reg.clear()

    def _get_tuple_register(self, tuplename: str):
        try:
            return self._vt_tuple_reg[tuplename]
        except KeyError:
            self._vt_tuple_reg[tuplename] = reg = _InstanceHPTupleRegister(name=tuplename, parent=self)
            return reg

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
        if self.closed:
            return
        if change["name"] == "_vt_reg_value_traits":
            handler = self._vt_on_reg_value_traits_change
        elif change["name"] == "_vt_reg_value_traits_persist":
            handler = self._vt_on_value_traits_persist_change
        elif isinstance(change["owner"], _InstanceHPTupleRegister):
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
                elif (obj_ := getattr(obj, n, defaults.NO_VALUE)) is not defaults.NO_VALUE:
                    # We tolerate non-traits in a HasTraits object assuming they are 'fixed' for the life of object in which they reside.
                    if isinstance(obj_, HasTraits):
                        obj = obj_
                        if cls._AUTO_VALUE and i == segments and obj.has_trait("value"):
                            yield (obj, "value")
                        continue
                    else:
                        break
                else:
                    msg = f"`{n}` is not a trait or attribute of {utils.fullname(obj)}"
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
        if tuplename not in cls._InstanceHPTuple:
            msg = (
                f"{tuplename=} is not a registered typed_instance_tuple "
                f"Register tuple names ={list(cls._InstanceHPTuple)}!"
            )
            raise KeyError(msg)
        return cls._InstanceHPTuple[tuplename].update_or_create_inst

    def _vt_update_reg_value_traits(self):
        pairs = set()
        if not self.closed:
            for dotname in self.value_traits:
                for pair in self._get_observer_pairs(self, dotname):
                    pairs.add(pair)
            self.set_trait("_vt_reg_value_traits", pairs)

    def _vt_update_reg_value_traits_persist(self):
        pairs: set[tuple[HasTraits, str]] = set()
        if not self.closed:
            for dotname in self.value_traits_persist:
                for pair in self._get_observer_pairs(self, dotname):
                    pairs.add(pair)
            self._vt_reg_value_traits_persist = pairs

    def _vt_update_reg_tuples(self, tuplename: str):
        if update_item_names := self._InstanceHPTuple[tuplename]._hookmappings.get("update_item_names", ()):
            items = getattr(self, tuplename)
            pairs = set()
            for obj in items:
                for dotname in update_item_names:
                    for owner, n in self._get_observer_pairs(obj, dotname):
                        pairs.add((owner, n))
            self._get_tuple_register(tuplename).set_trait("reg", pairs)

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
        if self.closed:
            return
        # `value` updated after "leaving context" (originally using context but only used here.)
        self.vt_updating = True
        self._vt_busy_updating_count = self._vt_busy_updating_count + 1
        try:
            if not self._ignore_change_cnt:
                self.on_change(change)
        except Exception as e:
            if self._vt_busy_updating_count == 1:
                self.on_error(e, "Change event error", change)
            raise
        finally:
            self._vt_busy_updating_count -= 1
            if not self._vt_busy_updating_count:
                self.vt_updating = False
                if (not self._ignore_change_cnt) and self._vt_init_complete and (not self.vt_validating):
                    self.set_trait("value", defaults.NO_VALUE)

    def _load_value(self, data: Literal[defaults._NoValue.token] | dict | Callable):
        if self.closed:
            return
        try:
            self.load_value(data)
        except Exception as e:
            self.on_error(e, "Error loading data", data)
            raise

    def add_value_traits(self, *names: str, delay: float | None = None):
        """Append names to value_traits.

        delay: if it is not None, it will be called with a delay.
            a delay = 0 is equivalent to `mb_async.call_soon`.
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

    json_default = to_dict  # for serialization

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
            data = orjson.dumps(data, default=json_default, option=option)
            if decode:
                return data.decode()
        except TypeError:
            raise
        except Exception:
            return json.dumps(data, default=json_default)
        else:
            return data

    def to_yaml(
        self, names: None | Iterable[str] = None, fs: AbstractFileSystem | None = None, path: str | None = None
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

        `InstanceHPTuples` change events are also delivered here, specify the
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
