import re
from typing import Dict, List

from .dependency_injector import DependencyInjector

CASE_PATTERN = re.compile(r"(?<!^)(?=[A-Z])")
DependencyGraph = Dict[str, List[str]]


class ServiceMeta(type):
    """
    For tracking which Services have been defined.
    """

    # Mapping from parameter name to class
    services: Dict[str, type] = {}

    def __new__(cls, name, bases, attrs):
        klass = type.__new__(cls, name, bases, attrs)
        if name != "Service":
            arg_name = snake_case(name)
            cls.services[arg_name] = klass
        return klass


class Service(metaclass=ServiceMeta):
    """
    All services should inherit from this class.

    Services are singleton objects which manage some server task.
    """

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


def create_services(injectables: Dict[str, object] = {}) -> Dict[str, Service]:
    """
    Resolve service dependencies and instantiate each service. This should only
    be called once.
    """
    injector = DependencyInjector()
    injector.add_injectables(**injectables)

    return injector.build_classes(ServiceMeta.services)


def snake_case(string: str) -> str:
    """
    Copied from:
    https://stackoverflow.com/questions/1175208/elegant-python-function-to-convert-camelcase-to-snake-case
    """
    return CASE_PATTERN.sub("_", string).lower()
