import asyncio
import hashlib
import os
import shutil
import tarfile
from datetime import datetime
from typing import IO

import aiocron
import aiohttp
import geoip2.database
from maxminddb.errors import InvalidDatabaseError

from .config import config
from .core import Service
from .decorators import with_logger
from .timing import Timer


@with_logger
class GeoIpService(Service):
    """
        Service for managing the GeoIp database. This includes an asyncio crontab
    which periodically checks if the current file is out of date. If it is, then
    the service will try to download a new file from tue url in ``server.config``.

        Provides an interface for getting data out of the database.
    """

    def __init__(self):
        self.refresh_file_path()
        config.register_callback("GEO_IP_DATABASE_PATH", self.refresh_file_path)

        self.db = None
        self.db_update_time = None

        self.check_geoip_db_file_updated()

    def refresh_file_path(self):
        self.file_path = config.GEO_IP_DATABASE_PATH

    async def initialize(self) -> None:
        await self.check_update_geoip_db()
        # crontab: min hour day month day_of_week
        # Run every Wednesday because GeoLite2 is updated every first Tuesday
        # of the month.
        self._update_cron = aiocron.crontab(
            "0 0 0 * * 3", func=self.check_update_geoip_db
        )
        self._check_file_timer = Timer(
            60 * 10, self.check_geoip_db_file_updated, start=True
        )

    def check_geoip_db_file_updated(self):
        """
            Checks if the local database file has been updated by a server admin
        and loads it if it has.
        """
        if not os.path.isfile(self.file_path):
            return

        if self.db is None:
            # We haven't loaded the file before
            self.load_db()
        else:
            assert self.db_update_time is not None
            # We have loaded the file, so check if it has been updated

            date_modified = datetime.fromtimestamp(
                os.path.getmtime(self.file_path)
            )
            if date_modified > self.db_update_time:
                self.load_db()

    async def check_update_geoip_db(self) -> None:
        """
            Check if the geoip database is old and update it if so.
        """
        if not config.GEO_IP_LICENSE_KEY:
            self._logger.warning(
                "GEO_IP_LICENSE_KEY not set! Unable to download GeoIP database!"
            )
            return

        self._logger.debug("Checking if geoip database needs updating")
        try:
            date_modified = datetime.fromtimestamp(
                os.path.getmtime(self.file_path)
            )
            delta = datetime.now() - date_modified

            if delta.days > config.GEO_IP_DATABASE_MAX_AGE_DAYS:
                self._logger.info("Geoip database is out of date")
                await self.download_geoip_db()
        except FileNotFoundError:    # pragma: no cover
            self._logger.warning("Geoip database is missing...")
            await self.download_geoip_db()
        except asyncio.TimeoutError:    # pragma: no cover
            self._logger.warning(
                "Failed to download database file! "
                "Check the network connection and try again"
            )
        except Exception as e:    # pragma: no cover
            self._logger.exception(e)
            raise e

        self.load_db()

    async def download_geoip_db(self) -> None:
        """
            Download the geoip database to a file. If the downloaded file is not
        a valid gzip file, then it does NOT overwrite the old file.
        """
        assert config.GEO_IP_LICENSE_KEY is not None

        self._logger.info("Downloading new geoip database")

        # Download new file to a temp location
        temp_file_path = "/tmp/geoip.mmdb.tar.gz"
        await self._download_file(
            config.GEO_IP_DATABASE_URL,
            config.GEO_IP_LICENSE_KEY,
            temp_file_path
        )

        # Unzip the archive and overwrite the old file
        try:
            with tarfile.open(temp_file_path, "r:gz") as tar:
                f_in = extract_file(tar, "GeoLite2-Country.mmdb")
                with open(self.file_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
        except (tarfile.TarError) as e:    # pragma: no cover
            self._logger.warning("Failed to extract downloaded file!")
            raise e
        self._logger.info("New database download complete")

    async def _download_file(self, url: str, license_key: str, file_path: str) -> None:
        """
            Download a file using aiohttp and save it to a file.

            :param url: The url to download from
            :param file_path: Path to save the file at
        """

        chunk_size = 1024
        params = {
            "edition_id": "GeoLite2-Country",
            "license_key": license_key,
            "suffix": "tar.gz"
        }

        async def get_checksum(session):
            async with session.get(url, params={
                **params,
                "suffix": params["suffix"] + ".md5"
            }, timeout=60 * 20) as resp:
                return await resp.text()

        async def get_db_file_with_checksum(session):
            hasher = hashlib.md5()
            async with session.get(url, params=params, timeout=60 * 20) as resp:
                with open(file_path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        hasher.update(chunk)

            return hasher.hexdigest()

        async with aiohttp.ClientSession(raise_for_status=True) as session:
            checksum, our_hash = await asyncio.gather(
                get_checksum(session),
                get_db_file_with_checksum(session)
            )

        if checksum != our_hash:
            raise Exception(
                f"Hashes did not match! Expected {checksum} got {our_hash}"
            )

    def load_db(self) -> None:
        """
            Loads the database into memory.
        """
        try:
            # Set the time first, if the file is corrupted we don't need to try
            # loading it again anyways
            self.db_update_time = datetime.now()
            self.db = geoip2.database.Reader(self.file_path)
            self._logger.info(
                "File loaded successfully from %s", self.file_path
            )
        except (InvalidDatabaseError, FileNotFoundError, ValueError):
            self._logger.exception(
                "Failed to load maxmind db! Maybe the download was interrupted"
            )

    def country(self, address: str) -> str:
        """
            Look up an ip address in the db and return it's country code.
        """
        default_value = ""
        if self.db is None:
            return default_value

        try:
            return str(self.db.country(address).country.iso_code)
        except geoip2.errors.AddressNotFoundError:
            return default_value
        except ValueError as e:    # pragma: no cover
            self._logger.exception("ValueError: %s", e)
            return default_value


def extract_file(tar: tarfile.TarFile, name: str) -> IO[bytes]:
    """
    Helper for getting a file handle to the database file in the tar archive.
    This is needed because we don't necessarily know the name of it's containing
    folder.

    :raises: TarError if the tar archive does not contain the databse file
    """
    mmdb = next(
        (m for m in tar.getmembers() if
            m.name.endswith(name)
            and m.isfile()),
        None
    )
    if mmdb is None:
        # Because we verified the checksum earlier, this should only be
        # possible if maxmind actually served us a bad file
        raise tarfile.TarError("Tar archive did not contain the database file!")

    f = tar.extractfile(mmdb)

    if f is None:
        raise tarfile.TarError("Tar archive did not contain the database file!")

    return f
