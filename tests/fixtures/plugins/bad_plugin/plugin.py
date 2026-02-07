from squadpy.plugin import Plugin


class BadPlugin(Plugin):
    name = "Bad Plugin"
    description = "Fails on enable"

    async def on_enable(self):
        raise RuntimeError("Intentional failure")
