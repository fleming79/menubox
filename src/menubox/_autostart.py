from __future__ import annotations

import ipylab

import menubox as mb


class IpylabPlugin:
    def observe_ipylab_log_level(self, change: mb.ChangeType):
        def refresh_all_menuboxes():
            for inst in tuple(mb.Menubox._instances.values()):
                if isinstance(inst, mb.Menubox) and not inst.closed and inst.view:
                    inst.mb_refresh()

        if change["owner"].log_level == ipylab.log.LogLevel.DEBUG:  # type: ignore
            mb.log.START_DEBUG(to_stdio=False)
            refresh_all_menuboxes()
        elif mb.DEBUG_ENABLED:
            mb.DEBUG_ENABLED = False
            refresh_all_menuboxes()

    @ipylab.hookimpl(specname="autostart_once")
    async def connect_log(self, app: ipylab.App):
        app.observe(self.observe_ipylab_log_level, names="log_level")

    @ipylab.hookimpl(specname="autostart_once")
    async def load_css_stylesheet(self, app: ipylab.App):
        import menubox.css

        stylesheet = await menubox.css.MenuboxCSSStyleSheet().ready()
        variables = {}
        ss = ""
        for s, v in reversed(menubox.plugin_manager.hook.add_css_stylesheet()):
            ss += s
            variables.update(v)
        await stylesheet.load_stylesheet(ss, variables)
