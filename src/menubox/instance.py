from __future__ import annotations

import asyncio
import functools
import inspect
import weakref
from typing import TYPE_CHECKING, Any, Literal, NotRequired, ParamSpec, Self, TypedDict, TypeVar

import ipywidgets as ipw
import traitlets
from mergedeep import Strategy, merge

import menubox as mb
from menubox import utils
from menubox.defaults import NO_VALUE, _NoValue, is_no_value
from menubox.hasparent import HasParent
from menubox.trait_types import Bunched
from menubox.utils import iterflatten

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

__all__ = ["InstanceHP", "instanceHP_wrapper"]


T = TypeVar("T")
P = ParamSpec("P")


class IHPConfig(TypedDict):
    parent: HasParent
    name: str
    klass: type
    args: tuple
    kwgs: dict


class IHPDlinkType(TypedDict):
    """A TypedDict template to use with `InstanceHP.configure`."""

    source: tuple[str, str]  # Dotted name of HasTraits object relative to parent, trait name
    target: str  # The trait name of the Instance to dlink
    transform: NotRequired[Callable[[Any], Any]]


class InstanceHP(traitlets.ClassBasedTraitType[T, type[T]]):
    __slots__ = [
        "create",
        "read_only",
        "allow_none",
        "load_default",
        "set_parent",
        "dlink",
        "add_classes",
        "on_replace_discontinue",
    ]
    _klass: type[T] | None = None
    if TYPE_CHECKING:
        name: str  # type: ignore

    def class_init(self, cls, name):
        if issubclass(cls, HasParent):
            cls._InstanceHP[name] = self  # type: ignore # Register
        else:
            msg = (
                f"Setting {cls.__name__}.{name} = InstanceHP(...) is invalid "
                f"because {cls} is not a subclass of HasParent."
            )
            raise TypeError(msg)
        return super().class_init(cls, name)

    def __init__(self, klass: type[T], *args, **kwgs: Any) -> None:
        """InstanceHP is an Instance type class  to spawn the instance of
        `klass(*args, **kwargs)` in the `HasParent` (parent) object.

        This class replaces `traitlets.Instance` providing the necessary customisation
        to simplify construnction cutting the need to define "default" decorators by
        99%. Notably, 'parent' is inserted into **kwargs for `HasParent` subclasses
        (configurable with the `configure` method).

        It's design is analogous to functools.partial such that *args and **kwgs are
        passed to the klass during instantion along with parent (if relevant). Default
        settings will load the 'default' but can also be overridden with the `configure` method.

        Parameters
        ----------
        klass : str | HasParent | object
            The class that forms the basis for the trait.  Class names
            can also be specified using the name of the class as a string.
            If the string contains a dot `.` It will be resolved.
            Else it is assumed to be an subclass of `HasParent`.
        *args
            Positional args passed to klass default.
        **kwgs
            Extra kwargs passed to to klass default.

        `configure`
        ----
        See also .configure for further detail.

        """
        if isinstance(klass, str):
            self.klass_name = klass
        elif issubclass(klass, HasParent) or inspect.isclass(klass):  # type: ignore
            self._klass = klass  # type: ignore
        else:
            msg = f"{klass} is not a class or string!"
            raise TypeError(msg)
        if "parent" in kwgs:
            msg = "`parent`is an invalid argument. Use the `set_parent` tag instead."
            raise ValueError(msg)
        super().__init__(allow_none=False, read_only=True)
        self.args = args
        self.kwgs = kwgs
        self.configure()

    @property
    def klass(self) -> type[T]:
        if not self._klass:
            self._klass = self.get_class(self.klass_name)
        return self._klass

    @classmethod
    def get_class(cls, name: str) -> type[T]:
        """get the class for name or fully qualified name"""
        try:
            return HasParent._CLASS_DEFINITIONS[name.split(".")[-1]]  # type: ignore
        except KeyError as e:
            if "." in name:
                return traitlets.import_item(name)
            msg = f"'{name}' is not a registered class.\nValid options are {list(HasParent._CLASS_DEFINITIONS)}"
            raise ValueError(msg) from e

    @property
    def info_text(self):  # type: ignore
        return f"an instance of `{self.klass.__qualname__}` {'or `None`' if self.allow_none else ''}"

    def set(self, obj: HasParent, value: Any) -> None:  # type: ignore
        new_value = self._validate(obj, value)
        assert self.name is not None  # noqa: S101
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
            self._value_changed(obj, old_value, new_value)
            obj._notify_trait(self.name, old_value, new_value)

    def get(self, obj: HasParent, cls: Any = None) -> T | None:  # type: ignore
        try:
            value = obj._trait_values[self.name]  # type: ignore
            if getattr(value, "discontinued", False) and not obj.discontinued:
                # This object has been discontinued, so a new default should be obtained
                obj._trait_values.pop(self.name, None)
                raise KeyError  # noqa: TRY301
        except KeyError:
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
            if isinstance(value, traitlets.HasTraits):
                self._value_changed(obj, None, value)
                obj._notify_observers(Bunched(name=self.name, old=None, new=value, owner=obj, type="change"))
            if getattr(self, "children_mode", "") == "monitor":
                from menubox.synchronise import ChildrenSetter

                home = getattr(obj, "home", "default")
                ChildrenSetter(home=home, parent=obj, name=self.name, items=self.children)
            return value  # type: ignore
        except Exception as e:
            # This should never be reached.
            msg = "Unexpected error in TraitType: default value not set properly"
            raise traitlets.TraitError(msg) from e
        else:
            return value  # type: ignore

    def default(self, obj: HasParent, override: None | dict = None) -> T | None:  # type: ignore
        try:
            if override is None and not self.load_default:
                if self.allow_none:
                    return None
                msg = f'Both `load_default` and `allow_none` are False for "{obj.__class__.__name__}.{self.name}".'
                raise RuntimeError(msg)  # noqa: TRY301
            kwgs = dict(self.kwgs)
            if issubclass(self.klass, HasParent) and self.set_parent:
                kwgs["parent"] = obj
                kwgs["_ptname"] = self.name
            if override:
                if isinstance(override, dict):
                    kwgs = kwgs | override
                elif not isinstance(override, bool):
                    obj.log.warning(
                        f"'{utils.fullname(obj)}.{self.name}' provided "
                        f"{override=} is not a dict and will be returned 'as is'."
                    )
                    return override
            if children := getattr(self, "children", None):
                kwgs["children"] = obj.get_widgets(children, skip_hidden=False, show=True)
            name: str
            if self.dynamic_kwgs:
                for name, value in self.dynamic_kwgs.items():
                    if callable(value):
                        kwgs[name] = value(
                            IHPConfig(parent=obj, name=self.name, klass=self.klass, args=self.args, kwgs=kwgs)
                        )
                    elif value == "self":
                        kwgs[name] = obj
                    else:
                        kwgs[name] = utils.getattr_nested(obj, value, hastrait_value=False)
            create = self.create
            if not is_no_value(create):
                if isinstance(create, str):
                    create = getattr(obj, create)
                if callable(create):
                    return create(IHPConfig(parent=obj, name=self.name, klass=self.klass, args=self.args, kwgs=kwgs))  # type: ignore # type: T
            return self.klass(*(self.args), **kwgs)  # type:ignore[operator]
        except Exception as e:
            obj.on_error(e, f"instance for trait '{self.name}'", self)
            raise

    def _validate(self, obj: HasParent, value):
        if value is not None and not isinstance(value, self.klass):
            if obj.trait_has_value(self.name):
                value_ = getattr(obj, self.name)
                if isinstance(value_, self.klass):
                    return value_
            value = self.default(obj, value)  # type: ignore
        value = super()._validate(obj, value)
        if value is None:
            return value
        if self.set_parent and hasattr(value, "_ptname"):
            value.parent = obj  # type: ignore
            value.set_trait("_ptname", self.name)  # type: ignore
        return value

    def validate(self, obj: HasParent, value) -> T | None:
        if not self.klass:
            msg = f"klass has not been set for the InstanceHP object: {obj.__class__}.{self.name}"
            raise RuntimeError(msg)
        if isinstance(value, self.klass):  # type:ignore[arg-type]
            return value
        if value is None and not self.allow_none:
            msg = (
                f"None is not allowed for the InstanceHP trait `{obj.__class__.__name__}.{self.name}`. "
                f"Use `.configure(allow_none=True)` "
                "to permit it."
            )
            raise RuntimeError(msg)
        self.error(obj, value)  # noqa: RET503

    def _value_changed(self, obj: HasParent, old: Any | None, new: Any | None):
        if isinstance(new, ipw.Button):
            for name in self.on_click:
                self._register_on_click(obj, name, new)
        if isinstance(self.set_attrs, dict):
            for k, v in self.set_attrs.items():
                val = v
                if isinstance(val, str) and val.startswith("."):
                    val = val[1:]
                    val = obj if val == "self" else utils.getattr_nested(obj, val)
                elif callable(val):
                    config = IHPConfig(parent=obj, name=self.name, klass=self.klass, args=self.args, kwgs=self.kwgs)
                    val = val(config)
                utils.setattr_nested(new, k, val, setattr)
        if isinstance(self.dlink, tuple):
            target_obj = new
            for dlink in self.dlink:
                src_name, src_trait = dlink["source"]
                src_obj = obj if src_name == "self" else utils.getattr_nested(obj, src_name, hastrait_value=False)
                tgt_trait = dlink["target"]
                key = f"{id(obj)} {obj.__class__.__name__}.{self.name}.{tgt_trait}"
                if "." in tgt_trait:
                    class_name, tgt_trait = tgt_trait.rsplit(".", maxsplit=1)
                    target_obj = utils.getattr_nested(new, class_name, hastrait_value=False)
                transform = dlink.get("transform")
                if isinstance(transform, str):
                    transform = utils.getattr_nested(obj, transform, hastrait_value=False)
                if transform and not callable(transform):
                    msg = f"Transform must be callable but got {transform:!r}"
                    raise TypeError(msg)
                obj.dlink((src_obj, src_trait), target=None, transform=transform, key=key, connect=False)
                if isinstance(target_obj, traitlets.HasTraits):
                    obj.dlink((src_obj, src_trait), target=(target_obj, tgt_trait), transform=transform, key=key)
        if self.add_classes and isinstance(new, ipw.DOMWidget):
            for class_name in self.add_classes:
                new.add_class(class_name)
        if old is not None and old is not traitlets.Undefined:
            if getattr(old, "parent", None) is obj:
                old.parent = None
                old.set_trait("_ptname", "")
            if self.on_replace_discontinue:
                mb.utils.close_obj(old)

    def _register_on_click(self, obj: HasParent, name: str, b: ipw.Button):
        """Link the on_click to the Button.

        The callback is handled in a singular task. Returning an awaitable from the
        callback will be awaited
        """
        if mb.DEBUG_ENABLED and not callable(utils.getattr_nested(obj, name)):
            msg = f"`{utils.fullname(obj)}.{name}` is not callable!"
            raise TypeError(msg)
        if mb.DEBUG_ENABLED and name == "button_clicked" and not asyncio.iscoroutinefunction(obj.button_clicked):
            msg = f"By convention `{utils.fullname(obj)}.button_clicked` must be a coroutine function!"
            raise TypeError(msg)
        taskname = f"button_clicked[{id(obj)}] → {obj.__class__.__name__}.{self.name}"
        b.on_click(functools.partial(self._button_clicked, weakref.ref(obj), name, taskname))

    @staticmethod
    def _button_clicked(ref: weakref.ref, name: str, taskname: str, b: ipw.Button):
        obj: HasParent | None = ref()
        if obj:

            async def click_callback():
                callback = utils.getattr_nested(obj, name)
                if obj.BUTTON_BUSY_BORDER:
                    b.layout.border = obj.BUTTON_BUSY_BORDER
                try:
                    result = callback(b)
                    if inspect.isawaitable(result):
                        await result
                finally:
                    if obj.BUTTON_BUSY_BORDER:
                        b.layout.border = ""

            utils.run_async(click_callback(), name=taskname, obj=obj)

    # TODO: add overloads if allow_none is True/false
    def configure(
        self,
        *,
        load_default=True,
        set_parent=True,
        read_only=True,
        allow_none: bool | Literal[_NoValue.token] = NO_VALUE,
        create: str | Callable[[IHPConfig], T] | Literal[_NoValue.token] = NO_VALUE,
        dynamic_kwgs: dict[str, Any] | None = None,
        on_click: str | tuple[str, ...] = "button_clicked",
        set_attrs: dict[str, Any] | None = None,
        dlink: IHPDlinkType | tuple[IHPDlinkType, ...] | Literal[_NoValue.token] = NO_VALUE,
        on_replace_discontinue=True,
        add_classes=(),
    ) -> Self:
        """Configure everything about how the instance will be handled.

        Calling with no arguments is the default setting.

        When calling All settings will be overwritten except for:
        * create
        * dlink

        on_replace_discontinue: Bool
            Discontinue/close the previous instance if it is replaced.
            Note: HasParent will not close if its the property `KEEP_ALIVE` is True.
        allow_none : Optional bool
            default : True if (load_default is False) else False.
        set_parent: Bool [True]
            Set the parent to the owner of the trait (HasParent).
        dynamic_kwgs: dict
            mapping of dynamic kwargs to use during instantiation.
            values can be a mapping of dotted name to an attribute on the parent
            or a callable.
        create: str | callable
            The name of the create function in the parent to generate the default.
            create function is passed bunched settings:
                `Bunched(name:str, klass:type, args:tuple, kwgs:dict)`
        set_attrs: dict[str,any]
            Set the attributes of the instance during validation (after instantiation).
            Accepts dotted name keys. Uses `setattr` as the `default_setter`.
            **Dotted name values**:
                If the value is a string and starts with `.` the value will be replaced
                with the dotted name after the `.`.
            **Callable values**
                If the value is callable, the result of the callable is used. The callable
                is passed the structure `IHPConfig` noting that kwgs is updated in the same
                order as set_attrs.
        dlink: IHPDlinkType | tuple[IHPDlinkType]
            A mapping or tuple of mappings for dlinks to add when creating.
            'source': tuple[obj, str]
            'target: str
            transform: Callable[Any, Any]
                A function to convert the source value to the target value.
        add_classes: tuple
            A tuple of class names to add  (applies only to DOMWidget subclasses)
        Button **ONLY** Tags
        --------------------
        on_click: Str | Tuple
            Dotted name access to the on_click callbacks.
        """
        if allow_none is NO_VALUE:
            allow_none = load_default is False
        if is_no_value(create):
            create = getattr(self, "create", NO_VALUE)
        else:
            assert callable(create) or isinstance(create, str)  # noqa: S101
        self.create = create
        self.dynamic_kwgs = dict(dynamic_kwgs) if dynamic_kwgs else None
        self.on_click = tuple(iterflatten(on_click))
        self.set_attrs = dict(set_attrs) if set_attrs else None
        self.read_only = read_only
        self.allow_none = allow_none
        self.set_parent = set_parent
        self.load_default = load_default
        self.set_parent = set_parent
        self.on_replace_discontinue = on_replace_discontinue
        if dlink is NO_VALUE:
            dlink = getattr(self, "dlink", NO_VALUE)
        if isinstance(dlink, dict):
            dlink = (dlink,)
        assert dlink is NO_VALUE or isinstance(dlink, tuple)  # noqa: S101
        self.dlink = dlink
        self.add_classes = add_classes
        return self

    def set_children(
        self,
        *children: str | ipw.Widget | Callable[[], Iterable[ipw.Widget | str]],
        mode: Literal["on default", "monitor"] = "on default",
    ) -> Self:
        """The dotted names of widgets relative parent to use during instantiation.

        Children are collected from the parent using 'parent.get_widgets'.
        and passed as the keyword argument `children`= (<widget>,...) when creating a new instance.

        Additionally, if mode is 'monitor', the children will be updated as the state
        of the children is changed (including hide/show).

        mode: 'on default' | 'monitor'
            'on default': Load the children only when creating from default.
            'monitor' : Same as 'on default' plus monitor children and their visibility and
            reload on demand. The list of children must contain string names of traits
            (dotted paths accepted). When a widget is removed or replaced the children will be updated.
        """
        self.children = children
        self.children_mode = mode
        return self


def instanceHP_wrapper(
    klass: type[T],
    /,
    *,
    defaults: None | dict[str, Any] = None,
    strategy=Strategy.REPLACE,
    load_default=True,
    set_parent=True,
    read_only=True,
    allow_none: bool | Literal[_NoValue.token] = NO_VALUE,
    create: str | Callable[[IHPConfig], T] | Literal[_NoValue.token] = NO_VALUE,
    dynamic_kwgs: dict[str, Any] | None = None,
    on_click: str | tuple[str, ...] = "button_clicked",
    set_attrs: dict[str, Any] | None = None,
    on_replace_discontinue=True,
    dlink: IHPDlinkType | tuple[IHPDlinkType] | Literal[_NoValue.token] = NO_VALUE,
    tags: None | dict[str, Any] = None,
    add_classes=(),
):
    """
    A decorator style function to produce InstanceHP trait for klass.

    Note: the returned instance can also be configured.

    klass:
        The class to base the instance on.
    defaults:
        default values used in the create.
    strategy:
        How defaults are merged with the instance kwargs if a clash occurs with defaults.

    Configure
    ---------
    read_only: boo [ default False ]
        Make the trait read only.
    load_default: bool [default True]
    allow_none : Optional bool
        default : True if load_default is False else False
    tags:
        Default tags to apply (see tags).

    Usage:
    -----

    ```
    Dropdown = instanceHP_wrapper(ipw.Dropdown, defaults={"options": (1, 2, 3)})


    class Widget_Box(MenuBox):
        a = Dropdown(description="a")
        b = Dropdown(description="b").configure(load_default=False)


    wb = Widget_box()
    assert b.a.description == "a"
    wb2 = Widget_box()
    assert wb2.a is not wb
    ```

    """
    defaults_ = merge({}, defaults) if defaults else {}
    if allow_none is NO_VALUE:
        allow_none = load_default is False
    tags = dict(tags) if tags else {}

    # TODO : Requires py 3.12+ https://typing.readthedocs.io/en/latest/spec/constructors.html#converting-a-constructor-to-callable
    # Hopefully this will restore documentation to the Constructor.
    def instanceHP_factory(*args, **kwgs) -> InstanceHP[T]:
        """Returns an InstanceHP[klass] trait.

        Use this to add a trait to new subclass of HasParent.

        Specify *args and **kwgs to pass when creating the 'default' (when the trait default is requested).

        Follow the link (ctrl + click): function-> klass to see the class definition and what *args and **kwargs are available.
        """
        kw = merge({}, defaults_, kwgs, strategy=strategy)
        return (
            InstanceHP(klass, *args, **kw)
            .configure(
                read_only=read_only,
                allow_none=allow_none,
                load_default=load_default,
                set_parent=set_parent,
                on_replace_discontinue=on_replace_discontinue
                if isinstance(klass, str) or not issubclass(klass, ipw.Widget | HasParent)
                else False,
                create=create,
                set_attrs=set_attrs,
                dynamic_kwgs=dynamic_kwgs,
                on_click=on_click,
                dlink=dlink,
                add_classes=add_classes,
            )
            .tag(**tags)
        )

    return instanceHP_factory
