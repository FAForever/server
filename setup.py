import re
import subprocess
from distutils.core import setup
from pathlib import Path


def get_version() -> str:
    output = subprocess.run(
        [
            "git", "--git-dir", Path(__file__).parent / ".git",
            "describe", "--tags"
        ],
        capture_output=True
    ).stdout.decode().strip().split("-")
    # Output is either v1.3.5 if the tag points to the current commit or
    # something like this v1.3.5-11-g3b467ad if it doesn't

    version = ".".join(re.findall(r"\d+", output[0])) or "0.dev"
    if len(output) > 1:
        return f"{version}+{output[-1]}"
    else:
        return version


setup(
    version=get_version(),
)
