import mock
import logging
from src.decorators import with_logger, timed


def test_with_logger():
    @with_logger
    class testclass():
        pass
    assert isinstance(testclass()._logger, logging.Logger)


def test_timed_fun():
    logger = mock.Mock()

    @timed(logger=logger, limit=0)
    def something():
        return "Somevalue"
    assert something() == "Somevalue"
    logger.info.assert_any_call(mock.ANY)


def test_timed_method():
    logger = mock.Mock()

    class TestClass():
        @timed(logger=logger, limit=0)
        def something(self):
            return "Somevalue"
    assert TestClass().something() == "Somevalue"
    logger.info.assert_any_call(mock.ANY)


def test_timed_wraps_right():
    @timed()
    def somefun():
        return 'test'

    @timed
    def somefun():
        return 'test'
    assert somefun.__name__ == 'somefun'
