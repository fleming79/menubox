from __future__ import annotations

import asyncio
import contextlib
import functools
import inspect
import pathlib
import weakref
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, Generic, NoReturn, Self, override

import ipywidgets as ipw
import pandas as pd
import toolz
import traitlets
from ipylab.common import Fixed, Singular, import_item
from ipylab.log import IpylabLoggerAdapter
from traitlets import HasTraits

import menubox
import menubox as mb
from menubox import defaults as dv
from menubox import mb_async, trait_types, utils
from menubox.css import CSScls
from menubox.trait_types import ChangeType, NameTuple, ProposalType, R

__all__ = ["HasParent", "Link", "Dlink", "Home"]

if TYPE_CHECKING:
    from collections.abc import Generator, Hashable

    from menubox.instance import IHPChange, InstanceHP
    from menubox.repository import Repository


class Link:
    """Link traits from different objects together so they remain in sync.

    Modified copy - traitlets.link
    """

    updating = False

    def __init__(
        self,
        source: tuple[HasTraits, str],
        target: tuple[HasTraits, str],
        transform: tuple[Callable[[Any], Any], Callable[[Any], Any]] | None = None,
        *,
        obj: HasParent,
    ):
        traitlets.traitlets._validate_link(source, target)
        self.source, self.target = source, target
        if obj:
            if not isinstance(obj, HasParent):
                msg = f"obj must be an instance of HasParent not {type(obj)}"
                raise TypeError(msg)
            if obj.closed:
                msg = f"{obj=} is closed!"
                raise RuntimeError(msg)
        self.obj = obj
        self._transform, self._transform_inv = transform or (self._pass_through,) * 2
        self.link()

    def __repr__(self) -> str:
        return (
            f"Link source={self.source[0].__class__.__qualname__}.{self.source[1]} "
            f" target={self.target[0].__class__.__qualname__}.{self.target[1]}"
        )

    @contextlib.contextmanager
    def _busy_updating(self):
        self.updating = True
        try:
            yield
        finally:
            self.updating = False

    def _pass_through(self, x):
        return x

    def _obj_closed_observe(self, _: ChangeType):
        self.unlink()

    def link(self):
        setattr(
            self.target[0],
            self.target[1],
            self._transform(getattr(self.source[0], self.source[1])),
        )
        self.source[0].observe(self._update_target, names=self.source[1])
        self.target[0].observe(self._update_source, names=self.target[1])
        if self.obj:
            self.obj.observe(self._obj_closed_observe, names="closed")

    def _update_target(self, change: ChangeType):
        if self.updating or not self._transform:
            return
        if self.obj and self.obj.closed:
            self.unlink()
            return
        with self._busy_updating():
            try:
                setattr(self.target[0], self.target[1], self._transform(change["new"]))
                value = getattr(self.source[0], self.source[1])
                if not self.obj.check_equality(value, change["new"]):
                    msg = f"Broken link {self}: the source value changed while updating the target."
                    raise traitlets.TraitError(msg)  # noqa: TRY301
            except traitlets.TraitError as e:
                msg = (
                    f"Link {utils.fullname(self.source[0])}.{self.source[1]}->"
                    f"{utils.fullname(self.source[0])}.{self.target[1]}"
                )
                self.obj.on_error(e, msg, self)
                if mb.DEBUG_ENABLED:
                    raise

    def _update_source(self, change: ChangeType):
        if self.updating or not self._transform:
            return
        if self.obj and self.obj.closed:
            self.unlink()
            return
        with self._busy_updating():
            setattr(self.source[0], self.source[1], self._transform_inv(change["new"]))
            value = getattr(self.target[0], self.target[1])
            if not self.obj.check_equality(value, change["new"]):
                msg = f"Broken link {self}: the target value changed while updating the source."
                raise traitlets.TraitError(msg)

    def unlink(self):
        if self.obj:
            with contextlib.suppress(Exception):
                self.obj.unobserve(self._obj_closed_observe, names="closed")
        with contextlib.suppress(Exception):
            self.source[0].unobserve(self._update_target, names=self.source[1])
        with contextlib.suppress(Exception):
            self.target[0].unobserve(self._update_source, names=self.target[1])


class Dlink:
    """Link traits from different objects together so they remain in sync.

    Modified copy - traitlets.directional_link
    """

    updating = False

    def __init__(
        self,
        source: tuple[HasTraits, str],
        target: tuple[HasTraits, str],
        transform: Callable[[Any], Any] | None = None,
        *,
        obj: HasParent,
    ):
        traitlets.traitlets._validate_link(source, target)
        self._transform = transform or self._pass_through
        self.source, self.target = source, target
        if obj:
            if not isinstance(obj, HasParent):
                msg = f"obj must be an instance of HasParent not {type(obj)}"
                raise TypeError(msg)
            if obj.closed:
                msg = f"{obj=} is closed!"
                raise RuntimeError(msg)
        self.obj = obj
        self.link()

    def __repr__(self) -> str:
        return (
            f"Dlink source={self.source[0].__class__.__qualname__}.{self.source[1]} "
            f" target={self.target[0].__class__.__qualname__}.{self.target[1]}"
        )

    @contextlib.contextmanager
    def _busy_updating(self):
        self.updating = True
        try:
            yield
        finally:
            self.updating = False

    def _pass_through(self, x):
        return x

    def _obj_closed_observe(self, _: ChangeType):
        self.unlink()

    def link(self):
        try:
            setattr(
                self.target[0],
                self.target[1],
                self._transform(getattr(self.source[0], self.source[1])),
            )
        finally:
            self.source[0].observe(self._update, names=self.source[1])
        if self.obj:
            self.obj.observe(self._obj_closed_observe, names="closed")

    def _update(self, change):
        if self.updating or not self._transform:
            return
        if self.obj and self.obj.closed:
            self.unlink()
            return
        with self._busy_updating():
            try:
                setattr(self.target[0], self.target[1], self._transform(change["new"]))
            except Exception as e:
                self.obj.on_error(e, "dlink", self)
                if mb.DEBUG_ENABLED:
                    raise

    def unlink(self):
        if self.obj:
            with contextlib.suppress(Exception):
                self.obj.unobserve(self._obj_closed_observe, names="closed")
        with contextlib.suppress(Exception):
            self.source[0].unobserve(self._update, names=self.source[1])


class Parent(traitlets.Instance[R]):
    klass: type[R]  # type: ignore
    allow_none = True
    default_value = None
    read_only = False

    def __new__(cls, _klass: str | type[R], /) -> Parent[R | None]:
        return super().__new__(cls)

    def __init__(self, _klass: str | type[R], /) -> None:
        super().__init__(klass=_klass)

    def validate(self, obj: R, value: R | None | Any) -> R | None:
        if value is None:
            return None
        if value:
            p = value
            while hasattr(p, "parent"):
                if p is obj:
                    msg = f"Unable to set parent of {value!r} because {obj!r} is already a parent or ancestor!"
                    raise RuntimeError(msg)
                p = p.parent  # type: ignore
            return value
        msg = "Parent must be either an instance of HasParent or None"
        raise TypeError(msg)



class HasParent(Singular, Generic[R]):
    """A base class for objects that have a parent and can manage links to other objects.

    This class provides a foundation for creating objects that exist within a hierarchical
    structure, allowing for parent-child relationships and the management of links
    (both regular and dynamic) between related objects. It includes features for:
    - Maintaining a parent object.
    - Creating and managing links (using traitlets) to other objects.
    - Handling asynchronous initialization.
    - Closing and cleaning up resources.
    - Formatting strings with access to the object's namespace.
    - Handling errors and logging.
    - Managing InstanceHP traits for enabling/disabling features.
    - Waiting for asynchronous tasks to complete.
    - Retrieving widgets associated with the object.
    The class utilizes traitlets for managing attributes and observing changes,
    ensuring that changes to the parent or linked objects trigger appropriate updates.
    It also provides mechanisms for asynchronous initialization and cleanup,
    making it suitable for use in environments where asynchronous operations are common.

    # NOTE: This class requires a running event loop to initialize.
    """

    RENAMEABLE = True
    KEEP_ALIVE = False
    SINGLE_BY: ClassVar[tuple[str, ...] | None] = None
    _InstanceHP: ClassVar[dict[str, InstanceHP[HasParent, Any]]] = {}
    _HasParent_init_complete = False
    _prohibited_parent_links: ClassVar[set[str]] = set()
    _hp_reg_parent_link = traitlets.Set()
    _hp_reg_parent_dlink = traitlets.Set()
    _hp_reg_links = traitlets.Set()
    _hasparent_all_links: traitlets.Dict[str, Link | Dlink] = traitlets.Dict(
        default_value={},
        value_trait=traitlets.Union([traitlets.Instance(Link), traitlets.Instance(Dlink)]),
        key_trait=traitlets.Unicode(),
        read_only=True,
    )
    _button_register = Fixed[Self, dict[tuple[str, ipw.Button], Callable]](lambda _: {})

    parent_dlink = NameTuple()
    parent_link = NameTuple()
    name: traitlets.Unicode[str, str | bytes] = traitlets.Unicode()
    log = traitlets.Instance(IpylabLoggerAdapter)
    parent = Parent(HasTraits)
    tasks = traitlets.Set(traitlets.Instance(asyncio.Task), read_only=True)

    def __repr__(self):
        if self.closed:
            return super().__repr__()
        cs = "closed: " if self.closed else ""
        return f"<{cs}{self.__class__.__name__} name='{self.name}'>"

    def __init__(self, *, parent: R = None, **kwargs):
        """Initialize the HasParent class.

        Args:
            parent: The parent object.
            **kwargs: Keyword arguments to pass to the super class.
        """
        if self._HasParent_init_complete:
            return
        if self.SINGLE_BY and "name" in self.SINGLE_BY:
            name = self._single_key[self.SINGLE_BY.index("name")]
            self.set_trait("name", name)
            self.RENAMEABLE = False
        values = {}
        for name in tuple(kwargs):
            if name in self._InstanceHP:
                values[name] = kwargs.pop(name)
        self._HasParent_init_complete = True
        super().__init__(**kwargs)
        self.set_trait("parent", parent)
        for name, v in values.items():
            self.instanceHP_enable_disable(name, v)
        if self.init_async:
            assert asyncio.iscoroutinefunction(self.init_async)  # noqa: S101
        # Requires a running event loop.
        self.init_async = mb_async.run_async(self.init_async, tasktype=mb_async.TaskType.init, obj=self)  # type: ignore

    def __init_subclass__(cls, **kwargs) -> None:
        if cls.SINGLE_BY:
            assert isinstance(cls.SINGLE_BY, tuple)  # noqa: S101
            if cls.SINGLE_BY and "name" in cls.SINGLE_BY:
                cls.RENAMEABLE = False
        cls._cls_update_InstanceHP_register()
        super().__init_subclass__(**kwargs)

    @classmethod
    def get_single_key(cls, *args, **kwgs) -> Hashable:  # noqa: ARG003
        if not cls.SINGLE_BY:
            return None
        return tuple(cls if k == "cls" else kwgs[k] for k in cls.SINGLE_BY)

    @classmethod
    def _cls_update_InstanceHP_register(cls: type[HasParent]) -> None:
        tn_ = dict(cls._InstanceHP)
        for c in cls.mro():
            if c is __class__:
                break
            if issubclass(c, HasParent) and c._InstanceHP:
                # Need to copy other InstanceHP mappings in case of multiple subclassing
                for name in c._InstanceHP:
                    if name and name not in tn_:
                        tn_[name] = c._InstanceHP[name]
        cls._InstanceHP = tn_

    @classmethod
    def validate_name(cls, name: str) -> str:
        return name

    @traitlets.validate("name")
    def _hp_validate_name(self, proposal: ProposalType) -> str:
        if not self.RENAMEABLE and self.trait_has_value("name") and self.name:
            return self.name
        return self.validate_name(proposal["value"]).strip()

    @traitlets.validate("parent_link", "parent_dlink")
    def _parent_link_dlink_validate(self, proposal: ProposalType):
        if prohibited := self._prohibited_parent_links.intersection(proposal["value"]):
            msg = f"Prohibited links detected: {prohibited}"
            raise NameError(msg)
        links = []
        for link in toolz.unique(proposal["value"]):
            if not self.has_trait(link):
                msg = f"{utils.fullname(self)} does not have the trait '{link}'"
                raise AttributeError(msg)
            links.append(link)
        return tuple(links)

    @traitlets.default("log")
    def _default_log(self):
        return IpylabLoggerAdapter(self.__module__, owner=self)

    @traitlets.observe("parent", "parent_link", "parent_dlink")
    def _observe_parent(self, change: ChangeType):
        if change["name"] == "parent":
            if isinstance(change["old"], HasParent):
                with contextlib.suppress(Exception):
                    change["old"].unobserve(self._hp_parent_closed, "closed")
            if isinstance(change["new"], HasParent):
                change["new"].observe(self._hp_parent_closed, "closed")
        p_link = set()
        p_dlink = set()
        if self.parent:
            for n in self.parent_link:
                if self.parent.has_trait(n):
                    p_link.add((self.parent, n))
            for n in self.parent_dlink:
                if self.parent.has_trait(n):
                    p_dlink.add((self.parent, n))
        self._hp_reg_parent_link = p_link
        self._hp_reg_parent_dlink = p_dlink

    @traitlets.observe("_hp_reg_parent_link", "_hp_reg_parent_dlink")
    def _observe__hp_reg_parent_link(self, change: ChangeType):
        # Update links
        old = change["old"] if isinstance(change["old"], set) else set()
        mname = change["name"].rsplit("_", maxsplit=1)[1]
        method = self.link if mname == "link" else self.dlink
        # remove old links
        for _, name in set(old).difference(change["new"]):
            method((), (), key=f"{mname}_{name}", connect=False)  # type: ignore
        # add new links
        for parent, name in change["new"].difference(old):
            v = getattr(self, name)
            target = (v, "value") if isinstance(v, ipw.ValueWidget) and not isinstance(v, HasParent) else (self, name)
            val = getattr(parent, name)
            if isinstance(val, ipw.ValueWidget) and not isinstance(val, HasParent):
                source = val, "value"
            else:
                source = parent, name
            method(source, target, key=f"{mname}_{name}")

    def setter(self, obj, name: str, value):
        """Sets an attribute on an object, handling special cases for ipywidgets and ValueTraits.

        This function provides a flexible way to set attributes on objects, with specific
        handling for ipywidgets like Combobox and Selection widgets, as well as objects
        that utilize ValueTraits. It also supports setting values on HasTraits instances.
        Args:
            obj: The object on which to set the attribute.
            name (str): The name of the attribute to set.
            value: The value to set the attribute to.  Can be of any type, but special
                handling is provided for strings and ValueTraits.
        """
        from menubox import valuetraits as vt

        if isinstance(obj, ipw.Combobox) and name == "value":
            value = "" if value is None else str(value)
        if (
            isinstance(obj, ipw.widget_selection._Selection) and name == "value" and isinstance(value, str)
        ) and value == "":
            value = None
        val = getattr(obj, name, dv.NO_VALUE)
        if val is not dv.NO_VALUE:
            if isinstance(val, vt.ValueTraits) and not isinstance(value, vt.ValueTraits):
                obj = val
                name = "value"
                if callable(obj.setter):
                    utils.setattr_nested(obj, name, value, default_setter=obj.setter)
                    return
            elif (
                name != "value"
                and isinstance(val, HasTraits)
                and not isinstance(value, HasTraits)
                and val.has_trait("value")
            ):
                # Support for loading the value back into a HasTraits instance (Widget)
                obj = val
                name = "value"
        if isinstance(obj, HasTraits) and obj.has_trait(name):
            obj.set_trait(name, value)
        else:
            setattr(obj, name, value)

    def check_equality(self, a, b) -> bool:
        """Check objects are equal. Special handling for DataFrame."""
        if isinstance(a, pd.DataFrame):
            return a.equals(b)
        return a == b

    @property
    def repr_log(self):
        return self.__repr__()

    @override
    def add_traits(self, **_: Any) -> NoReturn:
        """-- DO NOT USE --

        The traitlets version of this function overwrites the class meaning
        that isininstance & issubclass fail causing unexpected behaviour.
        """

        msg = "Make a subclass instead."
        raise NotImplementedError(msg)

    def on_error(self, error: Exception, msg: str, obj: Any = None):
        """Logs an error message with exception information.

        Note: When overloading, do not raise the error, it should by the callee after this function returns.
            It may be useful to add a note to the exception if applicable.

        Args:
            error (Exception): The exception that occurred.
            msg (str): The error message to log.
            obj (Any, optional): An object associated with the error. Defaults to None.
        """
        self.log.exception(msg, obj=obj, exc_info=error)

    def _hp_parent_closed(self, _: ChangeType):
        try:
            self.close()
        except Exception as e:
            self.on_error(e, "close failed")
            if mb.DEBUG_ENABLED:
                raise

    def instanceHP_enable_disable(self, name: str, enable: bool | dict):
        """Enables or disables an InstanceHP trait.
        Args:
            name: The name of the instance HP to enable or disable.
            enable:
            If True or a dict, the instance HP is enabled. If a dict, it
            becomes the value of the instance HP. If False or None, the
            instance HP is disabled (set to None).
        Raises:
            KeyError: If the given name is not a valid instance HP.
        """

        if name not in self._InstanceHP:
            msg = f"{name=} is not an InstanceHP instance in {utils.fullname(self)} {list(self._InstanceHP)}"
            raise KeyError(msg)
        if enable in [False, None]:
            self.set_trait(name, None)
        elif self._trait_values.get(name) is None:
            self.set_trait(name, {} if enable is True else enable)

    def _reset_trait(self, name: str):
        """Reset the trait to an unloaded stated."""
        if name in self._trait_values:
            self.log.debug("InstanceHP resetting trait %s", name)
            if self._InstanceHP[name].allow_none:
                self.set_trait(name, None)
            self._trait_values.pop(name)

    def close(self, force=False):
        """Closes the object, disconnecting it from its parent and cleaning up resources.

        Designed to be compatible with `Widget.close`.

        Args:
            force (bool, optional): If True, forces the object to close even if KEEP_ALIVE is set. Defaults to False.
        """
        if self.closed or (self.KEEP_ALIVE and not force):
            return
        super().close()
        self.log.debug("Closed")
        self.set_trait("parent", None)
        if self.trait_has_value("_hasparent_all_links"):
            for link in self._hasparent_all_links.values():
                link.unlink()
            self._hasparent_all_links.clear()
        # Reset the object.
        for n in ["_trait_notifiers", "_trait_values", "_trait_validators"]:
            d = getattr(self, n, None)
            if isinstance(d, dict):
                d.clear()
        self.set_trait("closed", True)  # Need to restore this trait to false.

    def fstr(self, string: str, raise_errors=False, parameters: dict | None = None) -> str:
        """Formats string using fstr type notation.

        `self`, 'mb', `record` and `df` are available in the namespace.
        """
        if not string:
            return ""
        g = globals() | {"self": self, "mb": menubox} | (parameters or {})
        try:
            return utils.fstr(string, raise_errors=raise_errors, **g)
        except Exception:
            if raise_errors or mb.DEBUG_ENABLED:
                raise
            self.log.exception(f"Unable to process fstr for '{string=}' class={utils.fullname(self)}")
            return string

    def link(
        self,
        src: tuple[HasTraits, str],
        target: tuple[HasTraits, str],
        transform: tuple[
            Callable[[Any], Any],
            Callable[[Any], Any],
        ]
        | None = None,
        connect=True,
        key="",
    ):
        """Does link and keeps a reference link until closed.

        Designed to link the target to one source at a time.
        note: there is no need to use connect=False if simply updating the link for a
        new source.
        """
        k = key or f"{id(target[0])}_link_{target[1]}"
        if k in self._hasparent_all_links:
            self._hasparent_all_links.pop(k).unlink()
        if connect:
            link = Link(src, target, transform=transform, obj=self)
            self._hasparent_all_links[k] = link

    def dlink(
        self,
        src: tuple[HasTraits, str],
        target: tuple[HasTraits, str] | None,
        transform: Callable[[Any], Any] | None = None,
        connect=True,
        key="",
    ):
        """Does dlink and and keeps a reference link until closed.

        Designed to dlink the target to one source at a time.
        note: there is no need to use connect=False if simply updating the link for a
        new source.
        """
        if not key:
            if not target:
                msg = ""
                raise ValueError(msg)
            key = f"{id(target[0])}_dlink_{target[1]}"
        if key in self._hasparent_all_links:
            self._hasparent_all_links.pop(key).unlink()
        if connect:
            if not target:
                msg = "A target is required when connecting!"
                raise ValueError(msg)
            link = Dlink(src, target, transform=transform, obj=self)
            self._hasparent_all_links[key] = link

    async def init_async(self):
        """Perform additional initialisation tasks.

        When override this method ensure to call:

        ``` python
        await super().init_async()
        ```
        """
        if corofunc := getattr(super(), "init_async", None):
            await corofunc()

    async def wait_init_async(self) -> Self:
        if isinstance(self.init_async, asyncio.Task):
            try:
                await asyncio.shield(self.init_async)  # type: ignore
            except asyncio.CancelledError:
                if self.init_async.cancelled():
                    self.log.warning("init_async was cancelled before completing")
            except Exception as e:
                if inspect.iscoroutinefunction(self.init_async):
                    e.add_note("It looks like wait_init_async is being awaited somewhere which could cause a deadlock")
                raise
        return self

    def _handle_button_change(self, c: IHPChange[Self, ipw.Button]):
        if (b := c["old"]) and (cb := self._button_register.pop((c["name"], b), None)):
            b.on_click(cb, remove=True)
        if b := c["new"]:
            taskname = f"button_clicked[{id(b)}] → {self.__class__.__name__}.{c['name']}"
            self._button_register[(c["name"], b)] = on_click = functools.partial(
                self._on_click, weakref.ref(self), taskname
            )
            b.on_click(on_click)

    @classmethod
    def _on_click(cls, ref: weakref.ref[HasParent], taskname: str, b: ipw.Button):
        if self_ := ref():
            mb.mb_async.run_async(lambda: self_._button_clicked(b), name=taskname, obj=self_)

    async def _button_clicked(self, b: ipw.Button):
        try:
            b.add_class(CSScls.button_is_busy)
            await self.button_clicked(b)
        finally:
            b.remove_class(CSScls.button_is_busy)

    async def button_clicked(self, b: ipw.Button):
        """Handles button click events.

        When overriding this method, ensure to pass on click events by calling:

        ``` python
        await super().button_clicked(b)
        ```
        Args:
            b (ipw.Button): The button that was clicked.
        """

        button_clicked = getattr(super(), "button_clicked", None)
        if button_clicked:
            await button_clicked(b)

    async def wait_update_tasks(self, timeout=None) -> Self:
        await self.wait_tasks(
            mb_async.TaskType.update, mb_async.TaskType.init, mb_async.TaskType.click, timeout=timeout
        )
        return self

    async def wait_tasks(self, *tasktypes: mb_async.TaskType, timeout=None) -> Self:
        """Waits for tasks to complete belonging to this object, with an optional timeout.

        Tasks are added to this objects `tasks` set automatically when using `mb_async.run_async`.
        The tasktype is also specified when creating the task.

        Args:
            *tasktypes:  The TaskType wait for.
            If none are provided, all non-continuous tasks are waited for.
            timeout: Optional timeout in seconds. If exceeded, the waiting tasks are cancelled.
        Returns:
            Self: Returns the instance of the class.
        Raises:
            TypeError: If any of the provided tasktypes are not instances of TaskType.
        """

        if self.tasks:
            tasktypes_ = []
            for tt in tasktypes or mb_async.TaskType:
                if not isinstance(tt, mb_async.TaskType):
                    raise TypeError(str(tt))
                if tt is not mb_async.TaskType.continuous:
                    tasktypes_.append(tt)
            current_task = asyncio.current_task()
            if tasks := [
                t
                for t in self.tasks
                if t is not current_task and mb_async.background_tasks.get(t, mb_async.TaskType.general) in tasktypes_
            ]:
                async with asyncio.timeout(timeout):
                    await asyncio.shield(asyncio.gather(*tasks, return_exceptions=True))
        return self

    def get_widgets(
        self, *items: utils.GetWidgetsInputType, skip_disabled=False, skip_hidden=True, show=True
    ) -> Generator[ipw.Widget, None, None]:
        """Get widgets from a variety of input types ignoring invalid of closed items..

        Args:
            *items: A variable number of arguments, each of which can be:
            - A single widget.
            - A list of widgets.
            - A dictionary where values are widgets.
            - A callable that returns widgets or list of widgets.
            skip_disabled: If True, disabled widgets are skipped.
            skip_hidden: If True, hidden widgets are skipped.
            show: If True, the widget (Menubox) is displayed.

        Yields:
            Each widget found in the input items.
        """
        yield from utils.get_widgets(
            *items, skip_disabled=skip_disabled, skip_hidden=skip_hidden, show=show, parent=self
        )

    def get(self, name: str, default=None):
        """Same as dict.get method."""
        return getattr(self, name, default)


def to_safe_homename(name: str | Home | pathlib.Path):
    n = pathlib.PurePath(utils.sanatise_filename(str(name))).name
    if not n:
        msg = f"Unable convert {name=} to a valid home"
        raise NameError(msg)
    return n


class Home(HasParent):
    """A simple object to group objects together using common name.

    Home is singular by name and will return the same object when instantiated with the
    same name. Passing a name as an absolute path will set the repository url to that
    value. The name will take the base folder name, therefore it is not allowed to have
    use folders with the same name but different urls.

    Homes with name = 'default' or initiated with private=True are not registered. All
    other homes will appear in _REG.homes.
    """

    SINGLE_BY: ClassVar = ("name",)
    KEEP_ALIVE = True
    _HREG: _HomeRegister
    repository = Fixed[Self, "Repository"](
        lambda c: import_item("menubox.repository.Repository")(name="default", url=c["owner"]._url, home=c["owner"])
    )

    @classmethod
    def validate_name(cls, name: str) -> str:
        return to_safe_homename(name)

    @override
    @classmethod
    def get_single_key(cls, name: str | Home | pathlib.Path, **kwgs) -> Hashable:
        assert isinstance(name, Home | str | pathlib.Path)  # noqa: S101
        return (to_safe_homename(name),)

    def __new__(cls, name: str | Home | pathlib.Path, /, *args, **kwgs):
        if isinstance(name, Home):
            return name
        return super().__new__(cls, *args, name=name, **kwgs)

    def __init__(self, name: str | Home | pathlib.Path, /, *, private=False, **kwargs):
        if self._HasParent_init_complete:
            return
        path = name if isinstance(name, pathlib.Path) else pathlib.Path(str(name))
        self._url = path.absolute().as_posix() if path.is_absolute() else pathlib.Path().absolute().as_posix()
        super().__init__(**kwargs)
        if not private and not self.name.startswith("_"):
            self._HREG.set_trait("homes", (*self._HREG.homes, self))
        self.repository  # noqa: B018 # touch the repository to create it

    def __repr__(self):
        if self.closed:
            return super().__repr__()
        return f"<Home: {self.name}>"

    def __str__(self):
        return self.name

    async def get_repository(self, repository_name: str) -> Repository:
        from menubox.repository import Repository

        repo: Repository = Repository(name=repository_name, home=self)  # type: ignore
        await repo.wait_update_tasks()
        return repo


class _HomeTrait(traitlets.TraitType[Home, Home]):
    """Add this to HasParent classes that should have a home. The trait name must be 'home'."""

    def _validate(self, obj, value: Home | str):
        if not value:
            msg = """`home` is required!
                Hint: `home` can be specified as a string or inherited from a parent."""
            raise RuntimeError(msg)
        home = Home(value)
        if obj.trait_has_value("home") and home is not obj.home:
            msg = "Changing home is not allowed after it is set current={obj.home} new={home}"
            raise RuntimeError(msg)
        return home


class HasHome(HasParent):
    """A Subclass for grouping related objects together by home.

    `home` or `parent` must be specified during instance creation and cannot be changed.
    """

    home = _HomeTrait()

    def __repr__(self):
        if self.closed:
            return super().__repr__()
        cs = "closed: " if self.closed else ""
        home = f"{home}" if self._HasParent_init_complete and (home := getattr(self, "home", None)) else ""
        return f"<{cs}{self.__class__.__name__} name='{self.name}' {home}>"

    def __new__(cls, *, home: Home | str | None = None, parent: HasParent | None = None, **kwargs) -> Self:
        if has_home := "home" in cls._traits:
            if home:
                home = Home(home)
            elif isinstance(parent, HasHome):
                home = parent.home
            elif isinstance(parent, Home):
                home = parent
            else:
                msg = "'home' or 'parent' (with a home) must be provided for this class. 'home' may be a string."
                raise NameError(msg)
        inst = super().__new__(cls, home=home, parent=parent, **kwargs)
        if has_home and not inst._HasParent_init_complete:
            inst.set_trait("home", home)
        return inst


class _HomeRegister(traitlets.HasTraits):
    homes = trait_types.TypedTuple(traitlets.Instance(Home), read_only=True)

    @property
    def all_roots(self):
        return tuple(home.repository.root for home in self.homes if not getattr(home, "hidden", False))

    def _load_homes(self, all_roots: tuple[str, ...]):
        self.set_trait("homes", tuple(Home(root) for root in all_roots))


Home._HREG = _HomeRegister()
