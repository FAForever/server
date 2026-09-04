"""
Server framework

This module is completely self contained and could be extracted to its own
project.
"""

from .dependency_injector import DependencyInjector
from .service import Service, create_services

__all__ = (
    "DependencyInjector",
    "Service",
    "create_services"
)
