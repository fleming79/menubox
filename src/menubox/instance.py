from __future__ import annotations

import inspect
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Literal,
    NotRequired,
    ParamSpec,
    TypedDict,
    TypeVar,
    Unpack,
    overload,
)

import ipylab.common
import traitlets
from mergedeep import Strategy, merge

import menubox as mb
from menubox import utils
from menubox.defaults import NO_DEFAULT
from menubox.hasparent import HasParent
from menubox.trait_types import Bunched

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ipywidgets import Button

    from menubox.defaults import NO_DEFAULT_TYPE


__all__ = ["InstanceHP", "instanceHP_wrapper"]

S = TypeVar("S", bound=HasParent)
T = TypeVar("T")
P = ParamSpec("P")


class IHPCreate[S, T](TypedDict):
    name: str
    parent: S
    klass: type[T]
    kwgs: dict


class IHPChange[S, T](TypedDict):
    name: str
    parent: S
    old: T | None
    new: T | None


class ChildrenDottedNames(TypedDict):
    mode: Literal["monitor"]
    dottednames: tuple[str, ...]


class ChildrenNameTuple(TypedDict):
    mode: Literal["monitor_nametuple"]
    nametuple_name: str


class IHPSettings[S, T](TypedDict):
    set_parent: NotRequired[bool]
    add_css_class: NotRequired[str | tuple[str, ...]]
    dlink: NotRequired[IHPDlinkType | tuple[IHPDlinkType, ...]]
    on_click: NotRequired[str | Callable[[Button], Awaitable | None]]
    on_replace_close: NotRequired[bool]
    remove_on_close: NotRequired[bool]
    children: NotRequired[ChildrenDottedNames | ChildrenNameTuple | tuple[utils.GetWidgetsInputType, ...]]
    value_changed: NotRequired[str | Callable[[IHPChange[S, T]], None]]


class IHPDlinkType(TypedDict):
    """A TypedDict template to use with `InstanceHP.configure`."""

    source: tuple[str, str]  # Dotted name of HasTraits object relative to parent, trait name
    target: str  # The trait name of the Instance to dlink
    transform: NotRequired[Callable[[Any], Any]]


class InstanceHP(traitlets.TraitType, Generic[S, T]):
    """Descriptor for managing instances of a specific class as a trait.

    `InstanceHP` is a trait type that manages instances of a particular class.
    It handles instantiation, validation, and interaction with the managed
    instance, including setting parents, observing changes, and providing
    default values. It also supports plugin hooks for customization.
    The class provides a way to define and configure how instances of a class
    are created and managed as traits within a `HasParent` object. It supports
    lazy instantiation, default value loading, and allows customization through
    plugin hooks.
    Attributes:
        klass: The class to be managed. Can be a class type or a string
            representing the full path to the class.
        default_value: The default value for the trait. Defaults to None.
        allow_none: Whether None is a valid value for the trait. Defaults to True.
        read_only: Whether the trait is read-only. Defaults to True.
        load_default: Whether to load a default instance if no value is provided.
            Defaults to True.
        create: An optional callable that is used to create the instance.
        settings: A dictionary to store settings related to the instance.
        info_text: A property that returns a string describing the instance type.
    """

    klass: type[T]
    default_value: None = None
    allow_none = True
    read_only = True
    load_default = True

    if TYPE_CHECKING:
        name: str  # type: ignore
        settings: IHPSettings[S, T]

        @overload
        def __get__(self, obj: Any, cls: type[S]) -> T: ...  # type: ignore

    def class_init(self, cls, name):
        if issubclass(cls, HasParent):
            cls._InstanceHP[name] = self  # type: ignore # Register
        else:
            msg = (
                f"Setting {cls.__qualname__}.{name} = InstanceHP(...) is invalid "
                f"because {cls} is not a subclass of HasParent."
            )
            raise TypeError(msg)
        return super().class_init(cls, name)

    def __init__(self, klass: type[T] | str, create: Callable[[IHPCreate[S, T]], T] | None = None) -> None:
        self.settings = {}
        self._create = create
        if isinstance(klass, str):
            if "." not in klass:
                msg = f"{klass=} must be passed with the full path to the class inside the module"
                raise ValueError(msg)
            self._klass = klass
        elif inspect.isclass(klass):
            self._klass = klass
        else:
            msg = f"{klass=} must be either a class,  or the full path to the class!"
            raise TypeError(msg)
        super().__init__()

    def instance_init(self, obj: S):
        """Init an instance of TypedInstanceTuple."""
        super().instance_init(obj)
        utils.weak_observe(obj, self._on_obj_close, names="closed", pass_change=True)

    @property
    def info_text(self):  # type: ignore
        return f"an instance of `{self.klass.__qualname__}` {'or `None`' if self.allow_none else ''}"

    def __repr__(self):
        return f'InstanceHP<klass={self.klass.__name__}@{utils.fullname(self.this_class)}.{self.name}">'

    def __str__(self):
        return self.name

    def set(self, obj: S, value) -> None:  # type: ignore
        self.finalize()
        if isinstance(value, dict):
            value = self.default(obj, value)
        new_value = self._validate(obj, value)
        if isinstance(value, HasParent) and self.settings.get("set_parent"):
            # Do this early in case the parent is invalid.
            value.parent = obj
        try:
            old_value = obj._trait_values[self.name]
        except KeyError:
            old_value = self.default_value

        obj._trait_values[self.name] = new_value
        try:
            silent = bool(old_value == new_value)
        except Exception:
            # if there is an error in comparing, default to notify
            silent = False
        if silent is not True:
            # we explicitly compare silent to True just in case the equality
            # comparison above returns something other than True/False
            try:
                self._value_changed(obj, old_value, new_value)
            except Exception as e:
                obj.on_error(e, "Instance configuration error.")
            obj._notify_trait(self.name, old_value, new_value)

    def get(self, obj: S, cls: Any = None) -> T | None:  # type: ignore
        try:
            value: T | None = obj._trait_values[self.name]  # type: ignore
        except KeyError:
            self.finalize()
            # Obtain the default.
            default = self.default(obj)

            # Using a context manager has a large runtime overhead, so we
            # write out the obj.cross_validation_lock call here.
            _cross_validation_lock = obj._cross_validation_lock
            try:
                obj._cross_validation_lock = True
                value = self._validate(obj, default)
            finally:
                obj._cross_validation_lock = _cross_validation_lock
            obj._trait_values[self.name] = value  # type: ignore
            self._value_changed(obj, None, value)
            obj._notify_observers(Bunched(name=self.name, old=None, new=value, owner=obj, type="change"))
            return value  # type: ignore
        except Exception as e:
            # This should never be reached.
            msg = "Unexpected error in TraitType: default value not set properly"
            raise traitlets.TraitError(msg) from e
        else:
            return value  # type: ignore

    def finalize(self):
        """Finalizes the InstanceHP instance by resolving the class and calling the initialization hook.

        If the class is already resolved, this method does nothing. Otherwise, it imports the class if necessary,
        verifies that it is a class, stores it in the instance, and calls the 'instancehp_finalize' hook.
        """
        if hasattr(self, "klass"):
            return
        klass = self._klass if inspect.isclass(self._klass) else ipylab.common.import_item(self._klass)
        assert inspect.isclass(klass)  # noqa: S101
        self.klass = klass  # type: ignore
        mb.plugin_manager.hook.instancehp_finalize(inst=self, klass=klass, settings=self.settings)

    def default(self, parent: S, override: None | dict = None) -> T | None:  # type: ignore
        """Create a default instance of the managed class.

        This method attempts to create an instance of the class managed by this
        `InstanceHP`. It handles cases where a default instance is not explicitly
        loaded, allows for overriding default keyword arguments, and utilizes
        plugin hooks for customization.

        Args:
            parent: The parent object that "owns" this instance.  Used for
            error reporting and plugin hooks.
            override: An optional dictionary of keyword arguments to override
            the default keyword arguments.

        Returns:
            An instance of the managed class `T`, or `None` if `allow_none` is
            True and no default is loaded.

        Raises:
            RuntimeError: If both `load_default` and `allow_none` are False and
            no default has been set.
            Exception: Any exception raised during instance creation is caught,
            reported to the parent's `on_error` method, and then re-raised.
        """
        try:
            if not self.load_default and override is None:
                if self.allow_none:
                    return None
                msg = f"Both `load_default` and `allow_none` are `None` and the value is unset for {self!r}"
                raise RuntimeError(msg)  # noqa: TRY301
            kwgs = {}
            if self.settings:
                mb.plugin_manager.hook.instancehp_default_kwgs(inst=self, parent=parent, kwgs=kwgs)
            if override:
                kwgs = kwgs | override
            if self._create:
                return self._create(IHPCreate(parent=parent, name=self.name, klass=self.klass, kwgs=kwgs))
            return self.klass(**kwgs)

        except Exception as e:
            parent.on_error(e, f'Instance creation failed for "{utils.fullname(parent)}.{self.name}"', self)
            raise

    def _validate(self, obj: S, value) -> T | None:
        if value is None:
            if self.allow_none:
                return value
            msg = f"`None` is not allowed for {self}. Use `.configure(allow_none=True)` to permit it."
            raise traitlets.TraitError(msg)
        if isinstance(value, self.klass):  # type:ignore[arg-type]
            if obj._cross_validation_lock is False:
                value = self._cross_validate(obj, value)
            return value
        self.error(obj, value)  # noqa: RET503

    def _value_changed(self, parent: S, old: T | None, new: T | None):
        settings = self.settings
        if settings:
            change = IHPChange(name=self.name, parent=parent, old=old, new=new)
            mb.plugin_manager.hook.instancehp_on_change(inst=self, change=change)

    def _on_obj_close(self, change: mb.ChangeType):
        obj = change["owner"]
        if old := obj._trait_values.pop(self.name, None):
            self._value_changed(obj, old, None)  # type: ignore

    if TYPE_CHECKING:

        @overload
        def configure(
            self,
            *,
            read_only: bool = ...,
            allow_none: Literal[True],
            load_default: bool | NO_DEFAULT_TYPE = ...,
            **kwgs: Unpack[IHPSettings[S, T]],
        ) -> InstanceHP[S, T | None]: ...
        @overload
        def configure(
            self,
            *,
            read_only: bool = ...,
            allow_none: Literal[False],
            load_default: bool | NO_DEFAULT_TYPE = ...,
            **kwgs: Unpack[IHPSettings[S, T]],
        ) -> InstanceHP[S, T]: ...
        @overload
        def configure(
            self,
            *,
            read_only: bool = ...,
            allow_none: bool | NO_DEFAULT_TYPE = ...,
            load_default: Literal[False],
            **kwgs: Unpack[IHPSettings[S, T]],
        ) -> InstanceHP[S, T | None]: ...
        @overload
        def configure(
            self,
            *,
            read_only: bool = ...,
            allow_none: Literal[True] = ...,
            load_default: bool | NO_DEFAULT_TYPE = ...,
            **kwgs: Unpack[IHPSettings[S, T]],
        ) -> InstanceHP[S, T]: ...
        @overload
        def configure(
            self,
            *,
            read_only: bool = ...,
            allow_none: Literal[True] | NO_DEFAULT_TYPE = ...,
            load_default: bool | NO_DEFAULT_TYPE = ...,
            **kwgs: Unpack[IHPSettings[S, T]],
        ) -> InstanceHP[S, T]: ...

    # TODO: split out hooks. leave named as 'configure' for read_only, allow_none, Load_default
    def configure(
        self,
        *,
        read_only=True,
        allow_none: bool | NO_DEFAULT_TYPE = NO_DEFAULT,
        load_default: bool | NO_DEFAULT_TYPE = NO_DEFAULT,
        **kwgs: Unpack[IHPSettings[S, T]],
    ) -> InstanceHP[S, T] | InstanceHP[S, T | None]:
        """Configure how the instance is loaded and what hooks to use when it is changed.

        Configuration changes are merged using a nested replace strategy except as explained below.

        Additional custom hooks are also possible

        Defaults
        --------
        * load_default: True
        * allow_none: not load_default
        * read_only: True
        * set_parent: True [HasParent]
        * on_replace_close: True [HasParent | Widget]
        * on_click: "button_clicked" [Button]

        Parameters
        ----------
        on_replace_close: Bool
            Close the previous instance if it is replaced.
            Note: HasParent will not close if its the property `KEEP_ALIVE` is True.
        allow_none :  bool
            Allow the value to be None.
        set_parent: Bool [True]
            Set the parent to the parent of the trait (HasParent).
        dlink: IHPDlinkType | tuple[IHPDlinkType]
            A mapping or tuple of mappings for dlinks to add when creating.
            'source': tuple[obj, str]
            'target: str
            transform: Callable[Any, Any]
                A function to convert the source value to the target value.
        children: ChildrenDottedNames | ChildrenNameTuple | tuple[utils.GetWidgetsInputType, ...] <Boxes and Panels only>
            Children are collected from the parent using `parent.get_widgets`.
            and passed as the keyword argument `children`= (<widget>,...) when creating a new instance.

            Additionally, if mode is 'monitor', the children will be updated as the state
            of the children is changed (including add/remove hide/show).
            If mode is 'replace', the children will be replaced when the instance is replaced.
            If mode is 'monitor_nametuple', the children will be updated as the state
            of the children is changed (including add/remove hide/show).
            The children will be passed as a named tuple with the name specified in the
            `nametuple_name` field.
        add_css_class: str | tuple[str, ...] <DOMWidget **ONLY**>
            Class names to add to the instance. Useful for selectors such as context menus.
        on_click: Str | Tuple[str, ...] <Button **ONLY**>
            Dotted name access to the on_click callbacks.
        remove_on_close: bool
            If True, the instance will be removed from the parent when the instance is closed.
        """
        self.load_default = load_default if load_default is not NO_DEFAULT else self.load_default
        self.allow_none = allow_none if allow_none is not NO_DEFAULT else not load_default
        self.read_only = read_only
        if kwgs:
            merge(self.settings, kwgs, strategy=Strategy.REPLACE)  # type:ignore
        return self  # type: ignore


def instanceHP_wrapper(
    klass: Callable[P, T] | str,
    /,
    *,
    defaults: None | dict[str, Any] = None,
    strategy=Strategy.REPLACE,
    tags: None | dict[str, Any] = None,
    **kwargs: Unpack[IHPSettings[S, T]],
) -> Callable[P, InstanceHP[S, T]]:
    """Wraps the InstanceHP trait for use with HasParent classes.

    This function creates a factory that returns an InstanceHP trait,
    configured with the specified settings. It's designed to be used
    when adding a trait to a new subclass of HasParent.
    Args:
        klass: The class or a string representation of the class to be instantiated by the InstanceHP trait.
        defaults: A dictionary of default keyword arguments to be passed to the class constructor.
        strategy: The merging strategy to use when combining defaults with instance-specific keyword arguments.
                  Defaults to Strategy.REPLACE.
        tags: A dictionary of tags to be applied to the InstanceHP trait.
        **kwargs: Additional keyword arguments to be passed to the InstanceHP trait's configure method.
    Returns:
        A factory function that, when called, returns an InstanceHP trait instance.  The factory
        function accepts *args and **kwgs which are passed to the constructor of `klass` when the
        trait's default value is requested.
    Usage:
        Use this function to add an InstanceHP trait to a class that inherits from HasParent.
        The returned factory should be assigned as a class-level attribute.  When the trait
        is accessed for the first time on an instance of the class, the InstanceHP trait will
        be instantiated and configured.
    """

    defaults_ = merge({}, defaults) if defaults else {}
    tags = dict(tags) if tags else {}  # type: ignore

    def instanceHP_factory(*args: P.args, **kwgs: P.kwargs) -> InstanceHP[S, T]:
        """Returns an InstanceHP[klass] trait.

        Use this to add a trait to new subclass of HasParent.

        Specify *args and **kwgs to pass when creating the 'default' (when the trait default is requested).

        Follow the link (ctrl + click): function-> klass to see the class definition and what *args and **kwargs are available.
        """
        if defaults_:
            kwgs = merge({}, defaults_, kwgs, strategy=strategy)  # type: ignore
        instance: InstanceHP[S, T] = InstanceHP(klass, lambda c: c["klass"](*args, **kwgs | c["kwgs"]))  # type: ignore
        if kwargs:
            # TODO: rename to hooks
            instance.configure(**kwargs)
        if tags:
            instance.tag(**tags)
        return instance

    return instanceHP_factory
