from __future__ import annotations

import contextlib
import functools
import weakref
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, Self, cast, override

import ipywidgets as ipw
import pandas as pd
import toolz
import traitlets
from async_kernel import Caller
from ipylab.common import HasApp, Singular
from traitlets import HasTraits

import menubox
import menubox as mb
from menubox import defaults as dv
from menubox import mb_async, utils
from menubox.css import CSScls
from menubox.trait_factory import TF
from menubox.trait_types import RP, ChangeType, NameTuple, ProposalType, S

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Hashable

    from async_kernel.pending import Pending

    from menubox.instance import IHPChange, InstanceHP

__all__ = ["Dlink", "HasParent", "Link"]


class HasParent(Singular, HasApp, Generic[RP]):
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
    single_key: tuple[Hashable, ...]
    _InstanceHP: ClassVar[dict[str, InstanceHP[Self, Any, Any]]] = {}
    _HasParent_init_complete = False
    PROHIBITED_PARENT_LINKS: ClassVar[set[str]] = set()
    _hp_reg_parent_link = TF.Set(klass_=cast("type[set[Link]]", 0))
    _hp_reg_parent_dlink = TF.Set(klass_=cast("type[set[Dlink]]", 0))
    _hasparent_all_links = TF.DictReadOnly(
        klass_=cast("type[dict[Hashable, Link | Dlink]]", 0)
    )
    _button_register = TF.DictReadOnly(
        klass_=cast("type[dict[tuple[str, ipw.Button], Callable]]", 0)
    )
    parent_dlink = NameTuple()
    parent_link = NameTuple()
    name = TF.Str()
    parent = TF.parent(cast("type[RP]", "menubox.hasparent.HasParent")).configure(
        TF.IHPMode.X__N
    )
    tasks = TF.Set(klass_=cast("type[set[Pending[Any]]]", 0))

    def __repr__(self):
        if self.closed or not self._HasParent_init_complete:
            return super().__repr__()
        cs = "closed: " if self.closed else ""
        return f"<{cs}{self.__class__.__name__} name='{self.name}'>"

    def __init__(self, *, parent: RP | None = None, **kwargs):
        """Initialize the HasParent class.

        Args:
            parent: The parent object.
            **kwargs: Keyword arguments to pass to the super class.
        """
        if self._HasParent_init_complete:
            return
        if self.SINGLE_BY:
            assert isinstance(self.single_key, tuple)
        values = {}
        for name in tuple(kwargs):
            if name in self._InstanceHP:
                values[name] = kwargs.pop(name)
        self._HasParent_init_complete = True
        mb_async.run_async({"tasktype": mb_async.TaskType.init}, self.init_async)
        super().__init__(**kwargs)
        if parent:
            self.parent = parent
        # Requires a running event loop.
        for name, v in values.items():
            self.set_trait(name, v)

    async def init_async(self) -> None:
        """Perform additional initialisation tasks.

        When override this method ensure to call:

        ``` python
        await super().init_async()
        ```
        """
        if corofunc := getattr(super(), "init_async", None):
            await corofunc()

    def __init_subclass__(cls, **kwargs) -> None:
        if cls.SINGLE_BY:
            assert isinstance(cls.SINGLE_BY, tuple)
            if cls.SINGLE_BY and "name" in cls.SINGLE_BY:
                cls.RENAMEABLE = False
        cls._cls_update_InstanceHP_register()
        super().__init_subclass__(**kwargs)

    def __await__(self) -> Generator[Any, None, Self]:
        return self.wait_update_tasks(timeout=10).__await__()

    @classmethod
    def get_single_key(cls, *args, **kwgs) -> Hashable:  # noqa: ARG003
        if not cls.SINGLE_BY:
            return None
        try:
            return tuple(cls if k == "cls" else kwgs[k] for k in cls.SINGLE_BY)
        except KeyError:
            missing = [k for k in cls.SINGLE_BY if (k != "cls") and k not in kwgs]
            msg = f"The following SINGLE_BY keys were not provided {missing}"
            raise KeyError(msg) from None

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
        cls._InstanceHP = tn_  # pyright: ignore[reportAttributeAccessIssue]

    @classmethod
    def validate_name(cls, name: str) -> str:
        return name.strip()

    def _validate_name(self, name: str):
        if not self.RENAMEABLE and self.trait_has_value("name") and self.name:
            return self.name
        return self.validate_name(name)

    @traitlets.validate("name")
    def _hp_validate_name(self, proposal: ProposalType) -> str:
        return self._validate_name(proposal["value"])

    @traitlets.validate("parent_link", "parent_dlink")
    def _parent_link_dlink_validate(self, proposal: ProposalType):
        if prohibited := self.PROHIBITED_PARENT_LINKS.intersection(proposal["value"]):
            msg = f"Prohibited links detected: {prohibited}"
            raise NameError(msg)
        links = []
        for link in toolz.unique(proposal["value"]):
            if not self.has_trait(link):
                msg = f"{utils.fullname(self)} does not have the trait '{link}'"
                raise AttributeError(msg)
            links.append(link)
        return tuple(links)

    @traitlets.observe("closed")
    def _observe_hasparent_closed(self, _):
        for pen in self.tasks:
            pen.cancel(f"{self} is closed!")
        for inst in self._InstanceHP.values():
            inst._on_obj_close(self)
        for n in ["_trait_notifiers", "_trait_values", "_trait_validators"]:
            d = getattr(self, n, None)
            if isinstance(d, dict):
                d.clear()
        self.set_trait("closed", True)

    @traitlets.observe("parent", "parent_link", "parent_dlink")
    def _observe_parent(self, change: ChangeType):
        if change["name"] == "parent":
            if change["old"]:
                try:
                    change["old"].unobserve(
                        self._hp_parent_close_handle, names="closed"
                    )
                except Exception:
                    pass
            if isinstance(parent := change["new"], HasParent):
                self._hp_parent_close_handle = utils.weak_observe(
                    change["new"], self.close, names="closed", pass_change=False
                )
        p_link = set()
        p_dlink = set()
        if (parent := self.parent) is not None:
            for n in self.parent_link:
                if parent.has_trait(n):
                    p_link.add((self.parent, n))
            for n in self.parent_dlink:
                if parent.has_trait(n):
                    p_dlink.add((self.parent, n))
        self.set_trait("_hp_reg_parent_link", p_link)
        self.set_trait("_hp_reg_parent_dlink", p_dlink)

    @traitlets.observe("_hp_reg_parent_link", "_hp_reg_parent_dlink")
    def _observe__hp_reg_parent_link(self, change: ChangeType):
        # Update links
        old = change["old"] if isinstance(change["old"], set) else set()
        mname = change["name"].rsplit("_", maxsplit=1)[1]
        method = self.link if mname == "link" else self.dlink
        # remove old links
        for _, name in set(old).difference(change["new"]):
            method((), (), key=(mname, name), connect=False)  # pyright: ignore[reportArgumentType]
        # add new links
        for parent, name in change["new"].difference(old):
            v = getattr(self, name)
            target = (
                (v, "value")
                if isinstance(v, ipw.ValueWidget) and not isinstance(v, HasParent)
                else (self, name)
            )
            val = getattr(parent, name)
            if isinstance(val, ipw.ValueWidget) and not isinstance(val, HasParent):
                source = val, "value"
            else:
                source = parent, name
            method(source, target, key=(mname, name))

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
            isinstance(obj, ipw.widget_selection._Selection)
            and name == "value"
            and isinstance(value, str)
        ) and value == "":
            value = None
        val = getattr(obj, name, dv.NO_VALUE)
        if val is not dv.NO_VALUE:
            if isinstance(val, vt.ValueTraits) and not isinstance(
                value, vt.ValueTraits
            ):
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

    @staticmethod
    def check_equality(a, b) -> bool:
        """Check objects are equal.

        Special handling:
         - dict: checks both order and content are equal
         - DataFrame: uses `equals` method"""
        try:
            if isinstance(a, dict):
                return tuple(a) == tuple(b) and (a == b)
            return bool(a == b)
        except ValueError:
            if isinstance(a, pd.DataFrame):
                return a.equals(b)
        return False

    @property
    def repr_log(self):
        return self.__repr__()

    def on_error(self, error: BaseException, msg: str, obj: Any = None) -> None:
        """Logs an error message with exception information.

        Note: When overloading, do not raise the error, it should by the callee after this function returns.
            It may be useful to add a note to the exception if applicable.

        Args:
            error (Exception): The exception that occurred.
            msg (str): The error message to log.
            obj (Any, optional): An object associated with the error. Defaults to None.
        """
        if not isinstance(error, mb_async.PendingCancelled):
            self.log.exception(msg, obj=obj, exc_info=error)

    def enable_ihp(self, name: str, *, override: dict | None = None) -> Self:
        """Enable a InstanceHP trait.

        Passing an override will ensure the 'default' is always called.

        Args:
            name: The name of the instance HP to enable or disable.
            enable:
            If True or a dict, the instance HP is enabled. If a dict, it
            becomes the value of the instance HP. If False or None, the
            instance HP is disabled (set to None).
        Raises:
            KeyError: If the given name is not a valid instance HP.
        """

        ihp = self._InstanceHP[name]
        if override is not None or getattr(self, name, None) is None:
            self.set_trait(name, ihp.default(self, override=override or {}))
        return self

    def disable_ihp(self, name: str) -> Self:
        """Disables an InstanceHP trait."""
        ihp = self._InstanceHP[name]
        self.set_trait(name, ihp.default_value)
        return self

    def _reset_trait(self, name: str):
        """Reset the trait to an unloaded stated."""
        if name in self._trait_values:
            self.log.debug("InstanceHP resetting trait %s", name)
            if self._InstanceHP[name].allow_none:
                self.set_trait(name, None)
            self._trait_values.pop(name)

    def _notify_observers(self, event) -> None:
        """Notify observers of any event"""
        if event["type"] != "change":
            super()._notify_observers(event)
        elif notifiers := self._trait_notifiers.get(event["name"], {}):
            for c in (*notifiers.get("change", ()), *notifiers.get("all", ())):
                try:
                    if isinstance(c, traitlets.EventHandler) and c.name is not None:
                        getattr(self, c.name)(event)
                    else:
                        c(event)
                except AttributeError:
                    pass

    def close(self, force=False):
        """Closes the object, disconnecting it from its parent and cleaning up resources.

        Designed to be compatible with `Widget.close`.

        Args:
            force (bool, optional): If True, forces the object to close even if KEEP_ALIVE is set. Defaults to False.
        """
        if self.closed or (self.KEEP_ALIVE and not force):
            return
        super().close()
        self.set_trait("closed", True)  # Need to restore this trait to True.

    def fstr(
        self, string: str, raise_errors=False, parameters: dict | None = None
    ) -> str:
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
            self.log.exception(
                f"Unable to process fstr for '{string=}' class={utils.fullname(self)}"
            )
            return string

    def link(
        self,
        source: tuple[HasTraits, str],
        target: tuple[HasTraits, str],
        transform: tuple[
            Callable[[Any], Any],
            Callable[[Any], Any],
        ]
        | None = None,
        connect=True,
        key: Hashable = None,
    ) -> Link | None:
        """Does link and keeps a reference link until closed.

        Designed to link the target to one source at a time.
        note: there is no need to use connect=False if simply updating the link for a
        new source.
        """
        key = key or ("link", target)
        if current_link := self._hasparent_all_links.pop(key, None):
            current_link.close()
        if connect:
            self._hasparent_all_links[key] = Link(
                source, target, transform=transform, parent=self
            )
        return None

    def dlink(
        self,
        source: tuple[HasTraits, str],
        target: tuple[HasTraits, str],
        transform: Callable[[Any], Any] | None = None,
        connect=True,
        key: Hashable = None,
    ):
        """Does dlink and and keeps a reference link until closed.

        Designed to dlink target to one source at a time.
        note: there is no need to use connect=False if simply updating the link for a
        new source.
        """
        key = key or ("dlink", target)
        if current_link := self._hasparent_all_links.pop(key, None):
            current_link.close()
        if connect:
            self._hasparent_all_links[key] = Dlink(
                source, target, transform=transform, parent=self
            )

    def _handle_button_change(
        self, c: IHPChange[Self, ipw.Button], mode: TF.ButtonMode
    ) -> None:
        if (b := c["old"]) and (cb := self._button_register.pop((c["name"], b), None)):
            b.on_click(cb, remove=True)
        if b := c["new"]:
            taskname = (
                f"button_clicked[{id(b)}] → {self.__class__.__name__}.{c['name']}"
            )
            self._button_register[(c["name"], b)] = on_click = functools.partial(
                self._on_click, weakref.ref(self), taskname, mode
            )
            b.on_click(on_click)

    @classmethod
    def _on_click(
        cls,
        ref: weakref.ref[HasParent],
        key: str,
        /,
        mode: TF.ButtonMode,
        b: ipw.Button,
    ):
        if self_ := ref():
            if mode is TF.ButtonMode.cancel and (
                pen := mb_async.singular_tasks.get(key)
            ):
                pen.cancel()
                return
            mb.mb_async.run_async(
                {"obj": self_, "key": key}, self_._button_clicked, b, mode
            )

    async def _button_clicked(self, b: ipw.Button, mode: TF.ButtonMode):
        description = b.description
        b.add_class(CSScls.button_is_busy)
        if mode is TF.ButtonMode.cancel:
            b.description = "Cancel"
        elif mode is TF.ButtonMode.disable:
            b.disabled = True
        try:
            await self.button_clicked(b)
        finally:
            if mode is TF.ButtonMode.disable:
                b.disabled = False
            if mode is TF.ButtonMode.cancel:
                b.description = description
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
            mb_async.TaskType.update,
            mb_async.TaskType.init,
            mb_async.TaskType.click,
            timeout=timeout,
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
            current = Caller.current_pending()
            if tasks := [
                pen
                for pen in self.tasks
                if pen is not current
                and pen.metadata.get("tasktype", mb_async.TaskType.general)
                in tasktypes_
            ]:
                await Caller().wait(tasks, timeout=timeout)
        return self

    def get_widgets(
        self,
        *items: utils.GetWidgetsInputType,
        skip_disabled=False,
        skip_hidden=True,
        show=True,
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
            *items,
            skip_disabled=skip_disabled,
            skip_hidden=skip_hidden,
            show=show,
            parent=self,
        )

    def get(self, name: str, default=None):
        """Same as dict.get method."""
        return getattr(self, name, default)


class Link(HasParent):
    """Link traits from different objects together so they remain in sync.

    Inspiration traitlets.link
    """

    mode: Literal["link", "dlink"] = "link"
    _updating = False

    def __init__(
        self,
        source: tuple[HasTraits, str],
        target: tuple[HasTraits, str],
        transform: tuple[Callable[[Any], Any], Callable[[Any], Any]] | None = None,
        *,
        parent: S,  # pyright: ignore[reportInvalidTypeVarUse]
    ):
        self.source, self.target = source, target
        if parent.closed:
            msg = f"{parent=} is closed!"
            raise RuntimeError(msg)
        self.obj = parent
        if transform:
            self._transform, self._transform_inv = transform
        super().__init__(parent=parent)
        setattr(target[0], target[1], self._transform(getattr(source[0], source[1])))
        source[0].observe(self._update_target, names=source[1])
        if self.mode == "link":
            target[0].observe(self._update_source, names=target[1])

    def __repr__(self) -> str:
        return (
            f"Link source={self.source[0].__class__.__qualname__}.{self.source[1]} "
            f" target={self.target[0].__class__.__qualname__}.{self.target[1]}"
            f"parent={self.parent!r}"
        )

    def _transform(self, x, /):
        return x

    def _transform_inv(self, x, /):
        return x

    def _update_target(self, change: ChangeType):
        if self._updating or not self._transform:
            return
        if self.closed:
            return
        try:
            self._updating = True
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
        finally:
            self._updating = False

    def _update_source(self, change: ChangeType):
        if self._updating:
            return
        try:
            self._updating = True
            setattr(self.source[0], self.source[1], self._transform_inv(change["new"]))
            value = getattr(self.target[0], self.target[1])
            if not self.obj.check_equality(value, change["new"]):
                msg = f"Broken link {self}: the target value changed while updating the source."
                raise traitlets.TraitError(msg)
        finally:
            self._updating = False

    @override
    def close(self, force=True):
        if self.closed:
            return
        with contextlib.suppress(Exception):
            self.source[0].unobserve(self._update_target, names=self.source[1])
        with contextlib.suppress(Exception):
            self.target[0].unobserve(self._update_source, names=self.target[1])
        super().close()

    @override
    def on_error(self, error: BaseException, msg: str, obj: Any = None):
        msg = f"{self.__class__} error: {msg}"
        if self.parent:
            self.parent.on_error(error, msg, obj)
        else:
            super().on_error(error, msg, obj)


class Dlink(Link):
    mode = "dlink"

    def __init__(
        self,
        source: tuple[HasTraits, str],
        target: tuple[HasTraits, str],
        transform: Callable[[Any], Any] | None = None,
        *,
        parent: S,  # pyright: ignore[reportInvalidTypeVarUse]
    ):
        if transform:
            self._transform = transform
        super().__init__(source=source, target=target, parent=parent)
