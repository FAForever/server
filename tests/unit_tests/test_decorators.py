import logging
from unittest import mock

from server.decorators import timed, with_logger


def test_with_logger():
    @with_logger
    class TestClass:
        pass
    assert isinstance(TestClass()._logger, logging.Logger)


def test_timed_fun():
    logger = mock.Mock()

    @timed(logger=logger, limit=0)
    def something():
        return "Somevalue"
    assert something() == "Somevalue"
    logger.warning.assert_any_call(mock.ANY)


def test_timed_method():
    logger = mock.Mock()

    class TestClass:
        @timed(logger=logger, limit=0)
        def something(self):
            return "Somevalue"
    assert TestClass().something() == "Somevalue"
    logger.warning.assert_any_call(mock.ANY)


def test_timed_wraps_right():
    @timed()
    def somefun():
        return "test"

    @timed
    def somefun():
        return "test"
    assert somefun.__name__ == "somefun"
