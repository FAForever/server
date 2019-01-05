import asyncio
import gzip
import os
import shutil
import traceback
from datetime import datetime

import aiocron
import aiohttp
import geoip2.database
from maxminddb.errors import InvalidDatabaseError

from . import config
from .decorators import with_logger


@with_logger
class GeoIpService(object):
    """
        Service for managing the GeoIp database. This includes an asyncio crontab
    which periodically checks if the current file is out of date. If it is, then
    the service will try to download a new file from tue url in ``server.config``.

        Provides an interface for getting data out of the database.
    """

    def __init__(self):
        self.file_path = config.GEO_IP_DATABASE_PATH
        self.db = None

        # crontab: min hour day month day_of_week
        self._update_cron = aiocron.crontab('*/10 * * * *', func=self.check_update_geoip_db)
        asyncio.ensure_future(self.check_update_geoip_db())

    async def check_update_geoip_db(self) -> None:
        """
            Check if the geoip database is old and update it if so.
        """

        self._logger.debug("Checking if geoip database needs updating")
        try:
            date_modified = datetime.fromtimestamp(os.path.getmtime(self.file_path))
            delta = datetime.now() - date_modified

            if delta.days > config.GEO_IP_DATABASE_MAX_AGE_DAYS:
                self._logger.info("Geoip database is out of date")
                await self.download_geoip_db()
        except FileNotFoundError:  # pragma: no cover
            self._logger.warning("Geoip database is missing...")
            await self.download_geoip_db()
        except asyncio.TimeoutError:  # pragma: no cover
            self._logger.warning("Failed to download database file! "
                                 "Check the network connection and try again")
        except Exception as e:  # pragma: no cover
            self._logger.exception("Exception in GeoIpService")
            traceback.print_exc()
            raise e

        self.load_db()

    async def download_geoip_db(self) -> None:
        """
            Download the geoip database to a file. If the downloaded file is not
        a valid gzip file, then it does NOT overwrite the old file.
        """

        self._logger.info("Downloading new geoip database")

        # Download new file to a temp location
        temp_file_path = "/tmp/geoip.mmdb.gz"
        await self._download_file(config.GEO_IP_DATABASE_URL, temp_file_path)

        # Unzip the archive and overwrite the old file
        try:
            with gzip.open(temp_file_path, 'rb') as f_in:
                with open(self.file_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        except OSError:  # pragma: no cover
            self._logger.warning("Failed to unzip downloaded file!")
        self._logger.info("New database download complete")

    async def _download_file(self, url: str, file_path: str) -> None:
        """
            Download a file using aiohttp and save it to a file.

            :param url: The url to download from
            :param file_path: Path to save the file at
        """

        chunk_size = 1024
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=60 * 20) as resp:
                with open(file_path, 'wb') as f:
                    while True:
                        chunk = await resp.content.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)

    def load_db(self) -> None:
        """
            Loads the database into memory.
        """
        try:
            self.db = geoip2.database.Reader(self.file_path)
        except InvalidDatabaseError:
            self._logger.warning("Failed to load maxmind db! Maybe the download was interrupted")
            pass

    def country(self, address: str) -> str:
        """
            Look up an ip address in the db and return it's country code.
        """
        default_value = ''
        if self.db is None:
            return default_value

        try:
            return str(self.db.country(address).country.iso_code)
        except geoip2.errors.AddressNotFoundError:
            return default_value
        except ValueError as e:  # pragma: no cover
            self._logger.exception("ValueError: %s", e)
            return default_value
