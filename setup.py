import re
import subprocess
from distutils.core import setup

from setuptools import find_packages

import server


def get_version() -> str:
    output = subprocess.run(
        ["git", "describe", "--abbrev=0", "--tags"],
        capture_output=True
    ).stdout.decode().strip()

    m = re.match(r"v?(\d+(\.\d+(\.\d+)?)?)", output)
    if not m:
        return "dev"
    return m.groups()[0]


setup(
    name='Forged Alliance Forever Server',
    version=get_version(),
    packages=['server'] + find_packages(),
    url='http://www.faforever.com',
    license=server.__license__,
    author=server.__author__,
    author_email=server.__contact__,
    description='Lobby/game server project',
    include_package_data=True
)
