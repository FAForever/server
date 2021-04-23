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
    logger.warning.assert_called_once()


def test_timed_method():
    logger = mock.Mock()

    class TestClass:
        @timed(logger=logger, limit=0)
        def something(self):
            return "Somevalue"

    assert TestClass().something() == "Somevalue"
    logger.warning.assert_called_once()


def test_timed_wraps_right():
    @timed()
    def somefun_1():
        return "test"

    @timed
    def somefun_2():
        return "test"

    assert somefun_1.__name__ == "somefun_1"
    assert somefun_2.__name__ == "somefun_2"
