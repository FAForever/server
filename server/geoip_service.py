import aiocron
import aiohttp
import asyncio

from datetime import datetime
import gzip
import geoip2
import os
import shutil

from .decorators import with_logger
from . import config


@with_logger
class GeoIpService(object):
    def __init__(self):
        self.file_path = config.GEO_IP_DATABASE_PATH

        # crontab: min hour day month day_of_week
        self._update_cron = aiocron.crontab('0 0 * * *', func=self.check_update_geoip_db)
        asyncio.ensure_future(self.check_update_geoip_db())

    async def check_update_geoip_db(self) -> None:
        """ Check if the geoip database is old and update it if so. """

        self._logger.debug("Checking if geoip database needs updating")
        try:
            date_modified = datetime.fromtimestamp(os.path.getmtime(self.file_path))
            delta = datetime.now() - date_modified

            if delta.days > config.GEO_IP_DATABASE_MAX_AGE_DAYS:
                self._logger.info("Geoip database is out of date")
                await self.do_update_geoip_db()
        except FileNotFoundError:
            self._logger.warning("Geoip database is missing...")
            await self.do_update_geoip_db()

        self.load_db()

    async def do_update_geoip_db(self) -> None:
        self._logger.info("Downloading new geoip database")
        # Download new file to a temp location
        chunk_size = 1024
        temp_file_path = "/tmp/geoip.mmdb.gz"
        async with aiohttp.ClientSession() as session:
            async with session.get(config.GEO_IP_DATABASE_URL) as resp:
                with open(temp_file_path, 'wb') as f:
                    while True:
                        chunk = await resp.content.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
        # Unzip the archive and overwrite the old file
        with gzip.open(temp_file_path, 'rb') as f_in:
            with open(self.file_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        self._logger.info("New database download complete")

    def load_db(self) -> None:
        """ Loads the database into memory. """
        self.db = geoip2.database.Reader(self.file_path)

    def country(self, address: str) -> str:
        try:
            return str(self.db.country(address).country.iso_code)
        except (geoip2.errors.AddressNotFoundError, ValueError):
            return ''
