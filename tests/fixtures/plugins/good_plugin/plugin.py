from squadpy.plugin import Plugin, on_event


class GoodPlugin(Plugin):
    name = "Good Plugin"
    description = "A working test plugin"
    requires = ["rcon"]

    async def on_enable(self):
        self.logger.info("Good plugin enabled")

    @on_event("test_event")
    async def handle_test(self, event):
        pass
