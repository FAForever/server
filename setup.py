from distutils.core import setup

import server

setup(
    name='Forged Alliance Forever Server',
    version=server.__version__,
    packages=['server'],
    url='http://www.faforever.com',
    license=server.__license__,
    copyright=server.__copyright__,
    author=server.__author__,
    author_email=server.__contact__,
    description='Lobby/game server project'
)
