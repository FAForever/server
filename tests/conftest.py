import asyncio
import pytest
import sys
import logging
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-8s %(name)-20s %(message)s'))
logging.getLogger('quamash').setLevel(logging.INFO)
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.DEBUG)

import quamash
from quamash import QApplication

@pytest.fixture(scope='session')
def application():
    return QApplication([])

@pytest.fixture()
def loop(request, application):
    loop = quamash.QEventLoop(application)
    asyncio.set_event_loop(loop)

    def finalize():
        try:
            loop.close()
        finally:
            asyncio.set_event_loop(None)

    request.addfinalizer(finalize)
    return loop