from distutils.core import setup

from setuptools import find_packages

import server

setup(
    name='Forged Alliance Forever Server',
    version=server.__version__,
    packages=['server'] + find_packages(),
    url='http://www.faforever.com',
    license=server.__license__,
    author=server.__author__,
    author_email=server.__contact__,
    description='Lobby/game server project',
    include_package_data=True
)
