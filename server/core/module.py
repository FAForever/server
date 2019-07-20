class Module(object):
    def __init__(self) -> None:
        self.command_handlers = {}

    def route(self, command: str):
        """A decorator used to mark a function as a message handler"""
        def decorator(handler):
            self.command_handlers[command] = handler
            return handler
        return decorator
