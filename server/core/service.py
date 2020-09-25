import re
from typing import Any, Dict, List, Optional

from .dependency_injector import DependencyInjector

CASE_PATTERN = re.compile(r"(?<!^)(?=[A-Z])")
DependencyGraph = Dict[str, List[str]]


service_registry: Dict[str, type] = {}


class Service():
    """
    All services should inherit from this class.

    Services are singleton objects which manage some server task.
    """
    def __init_subclass__(cls, name: Optional[str] = None, **kwargs: Any):
        """
        For tracking which services have been defined.
        """
        super().__init_subclass__(**kwargs)
        arg_name = name or snake_case(cls.__name__)
        service_registry[arg_name] = cls

    async def initialize(self) -> None:
        """
        Called once while the server is starting.
        """
        pass  # pragma: no cover

    async def shutdown(self) -> None:
        """
        Called once after the server received the shutdown signal.
        """
        pass  # pragma: no cover

    def on_connection_lost(self, conn) -> None:
        """
        Called every time a connection ends.
        """
        pass  # pragma: no cover


def create_services(injectables: Dict[str, object] = {}) -> Dict[str, Service]:
    """
    Resolve service dependencies and instantiate each service. This should only
    be called once.
    """
    injector = DependencyInjector()
    injector.add_injectables(**injectables)

    return injector.build_classes(service_registry)


def snake_case(string: str) -> str:
    """
    Copied from:
    https://stackoverflow.com/questions/1175208/elegant-python-function-to-convert-camelcase-to-snake-case
    """
    return CASE_PATTERN.sub("_", string).lower()
