from collections.abc import Callable, Hashable
from typing import Generic, Self, cast, final, override

import ipywidgets as ipw
import traitlets
from pandas.io import clipboards

from menubox import mb_async
from menubox import trait_factory as tf
from menubox.instance import IHPCreate
from menubox.menuboxvt import MenuboxVTH
from menubox.pack import to_yaml
from menubox.persist import MenuboxPersist
from menubox.trait_types import MP, ChangeType, H, NameTuple
from menubox.valuetraits import InstanceHPTuple


@final
class ObjShuffle(MenuboxVTH, Generic[H, MP]):
    """A Menubox that can load MenuboxPersist instances into its shuffle box."""

    SINGLE_BY = ("klass", "home")
    RENAMEABLE = False
    pool = InstanceHPTuple[Self, MP](
        traitlets.Instance(MenuboxPersist), factory=lambda c: c["parent"].factory_pool(**c["kwgs"])
    ).hooks(
        update_item_names=("name", "versions"),
        set_parent=True,
        close_on_remove=False,
    )

    title_description = traitlets.Unicode("<b>{self.klass.__qualname__.replace('_','').capitalize()} set</b>")
    html_info = tf.HTML()
    info_html_title = ipw.HTML(layout={"margin": "0px 20px 0px 40px"})
    yaml_data = ipw.Textarea(layout={"width": "auto"})
    sw_obj = tf.Combobox(placeholder="Enter name or select existing", continuous_update=True)
    sw_version = tf.Dropdown(
        description="Version",
        tooltip="Select the version to show the details",
        layout={"width": "130px"},
    )
    button_show_obj = tf.AsyncRunButton(
        cast(Self, None),
        cfunc=lambda p: p._button_show_obj_on_click_async,
        description="Show",
        cancel_description="Loading",
        tooltip="Show selected item.",
        disabled=True,
    )
    button_scan_obj = tf.Button_main(description="↻", tooltip="Update options")
    button_clip_put = tf.Button_main(description="⎘", tooltip="Copy data to clipboard")
    box_info = tf.VBox()
    box_info_header = tf.HBox().hooks(
        set_children=("html_title", "sw_version", "button_clip_put", "html_info"),
    )
    box_details = tf.VBox()
    modal_info = tf.Modalbox(
        cast(Self, None),
        obj=lambda p: p.box_info,
        title="Details",
        box=lambda p: p.box_details,
    )
    box_shuffle_controls = tf.MenuboxHeader().hooks(
        set_children=("sw_obj", "button_scan_obj", "button_show_obj", "modal_info", "_get_template_controls")
    )
    box_center = None
    views = traitlets.Dict({"Main": ("box_shuffle_controls", "box_details", "box_shuffle")})
    value_traits = NameTuple(*MenuboxVTH.value_traits, "sw_obj", "sw_version")

    @override
    @classmethod
    def get_single_key(cls, name="default", **kwgs) -> Hashable:
        return super().get_single_key(name=name, **kwgs)

    def factory_pool(self, **kwgs):
        if self._factory:
            return self._factory(IHPCreate(name="", parent=self, kwgs=kwgs, klass=self.klass))
        return self.klass(**kwgs)

    @traitlets.observe("sw_obj")
    def _observe_sw_obj(self, change: ChangeType):
        if change["new"]:
            self.update_sw_obj_options()

    def list_stored_datasets(self) -> list[str]:
        """List the stored datasets for the klass."""
        return self.klass.list_stored_datasets(self.home)

    def __init__(self, *, klass: type[MP], factory: Callable[[IHPCreate], MP] | None = None, **kwgs):
        if self._HasParent_init_complete:
            return
        self.klass = klass
        self._factory = factory
        super().__init__(**kwgs)

    @override
    def on_change(self, change):
        super().on_change(change)
        if change["owner"] is self.sw_obj:
            self.button_show_obj.disabled = not self.sw_obj.value
        match change["name"]:
            case "name" | "versions":
                self.update_sw_obj_options()
                self.update_sw_version_options()
            case _:
                self.update_box_info()

    @override
    async def button_clicked(self, b: ipw.Button):
        await super().button_clicked(b)
        match b:
            case self.button_scan_obj:
                self.update_sw_obj_options()
            case self.button_clip_put:
                clipboards.to_clipboard(self.yaml_data.value, False)

    def update_sw_obj_options(self):
        self.sw_obj.options = self.list_stored_datasets()
        self.log.debug(f"updated sw_obj options. options={self.sw_obj.options}")

    def update_sw_version_options(self):
        self.sw_version.options = self.klass.get_persistence_versions(self.home, self.sw_obj.value, self.log)

    def get_obj(self, name: str) -> MP:
        """Get / create object by name from pool."""
        return self.get_tuple_obj("pool", name=name)

    async def _button_show_obj_on_click_async(self, **kwargs):
        obj = self.get_obj(self.sw_obj.value)
        self.sw_obj.value = ""
        self.load_shuffle_item(obj, **kwargs)
        return obj

    @mb_async.debounce(0.1)
    def update_box_info(self) -> None:
        self.update_sw_version_options()
        if name := self.sw_obj.value:
            versions = self.sw_version.options
            self.html_info.value = f" {len(versions)} version{'s' if len(versions) == 1 else ''}"
            if version := self.sw_version.value:
                data = self.klass.get_persistence_data(self.home, name, version)
                self.yaml_data.value = to_yaml(data, walkstring=True)
                self.info_html_title.value = f"<h3>{name} v{version}</h3>"
                self.box_info.children = (self.box_info_header, self.yaml_data)
            else:
                self.box_info.children = self.html_info, self.sw_version
        else:
            self.html_info.value = "<b>Insufficient detail</b>"
            self.box_info.children = (self.html_info,)
