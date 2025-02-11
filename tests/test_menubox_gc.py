import asyncio
import contextlib
import gc
import weakref

import ipywidgets as ipw

import menubox as mb
from menubox import utils

weakref_enabled = False
with contextlib.suppress(Exception):
    ipw.enable_weakreference()
    weakref_enabled = True


class MenuBoxM(mb.MenuBox):
    """
    Some docs
    ---------

    Documentation should be written in *Markdown*.

    ---


    """

    deleted = False

    def __del__(self):
        MenuBoxM.deleted = True
        super().__del__()


class ButtonM(ipw.Button):
    deleted = False

    def close(self):
        self.on_msg(self._handle_button_msg, True)
        self._click_handlers.callbacks = []
        super().close()

    def __del__(self):
        ButtonM.deleted = True
        super().__del__()


async def test_menubox_gc():
    mbox = MenuBoxM()
    await utils.wait_for(mbox.show())
    mbox.discontinue()
    await asyncio.sleep(0.2)
    del mbox
    gc.collect()
    assert MenuBoxM.deleted, "Garbage collection happens after discontinue is called."
    # Not at this stage - buttons appear to be a memory leak

    b = ButtonM()
    b.close()
    del b
    await asyncio.sleep(1)
    gc.collect()
    assert ButtonM.deleted, "Garbage collection happens after closing (using overload)."


async def test_ipywidgets_gc():
    candidates = {}
    for name, obj in ipw.__dict__.items():
        try:
            if issubclass(obj, ipw.Widget):
                candidates[name] = obj
        except Exception:
            pass
    added = set()
    collected = set()
    objs = weakref.WeakSet()
    options = ({}, {"options": [1, 2, 4]}, {"n_rows": 1}, {"options": ["A"]})
    for n, obj in candidates.items():
        if not weakref_enabled and n == "Button":
            continue
        w = None
        for kw in options:
            try:
                w = obj(**kw)
                break
            except Exception:
                pass
        if not w:
            print(f"skipping {n}")  # noqa: T201
            continue
        added.add(n)

        def on_delete(name=n):
            collected.add(name)

        weakref.finalize(w, on_delete)
        await asyncio.sleep(0.01)
        if not weakref_enabled:
            mb.utils.close_ipw(w)
        objs.add(w)
        del w
    await asyncio.sleep(0.01)
    gc.collect()

    diff = added.difference(collected)
    assert not diff, f"Widgets not garbage collected {diff}"
