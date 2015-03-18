import asyncio
import signal

from PySide.QtNetwork import QHostAddress

from src.FaGamesServer import FAServer
from config import Config
from tests.conftest import players, player_service, games, game


Config['global'] = dict()
Config['global']['lobby_ip'] = '127.0.0.1'

from quamash import QApplication, QEventLoop
#logging.getLogger('quamash').setLevel(logging.DEBUG)

loop = QEventLoop(QApplication([]))
asyncio.set_event_loop(loop)

stop = asyncio.Future()

def exit_handler(signame, what):
    print("Got %s %s" % (signame, what))
    stop.set_result(0)

@asyncio.coroutine
def poll_signal():
    while True:
        if stop.done():
            return
        yield from asyncio.sleep(1)

asyncio.async(poll_signal())

for signame in ('SIGINT', 'SIGTERM'):
    signal.signal(getattr(signal, signame), exit_handler)

p = players()
with FAServer(loop, player_service(p), games(game(p)), [], []) as server:
    address = QHostAddress.SpecialAddress.LocalHost
    server.listen(address, 8000)
    print("Server listening", flush=True)
    loop.run_until_complete(stop)

