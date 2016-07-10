import json
from functools import partial
import asyncio

import pkg_resources
from httplib2 import Http
from oauth2client.service_account import ServiceAccountCredentials
from server.config import API_TOKEN_URI, API_BASE_URL

CACERTS_FILE = pkg_resources.resource_filename('static', 'cacerts.txt')


class ApiAccessor:
    def __init__(self):
        self._service_account_credentials = ServiceAccountCredentials.from_p12_keyfile(
            'faf-server',
            'faf-server.pem',
            scopes='write_achievements write_events'
        )
        self._service_account_credentials.token_uri = API_TOKEN_URI

    async def api_get(self, path, player_id):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, partial(self.http(player_id).request, API_BASE_URL + path, "GET"))
        return result

    async def api_post(self, path, player_id, data=None, headers=None):
        headers = headers or {'Content-type': 'application/json'}
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(self.http(player_id).request, API_BASE_URL + path, "POST", headers=headers, body=json.dumps(data))
        )

        return result

    def http(self, sub=None):
        credentials = self._service_account_credentials.create_delegated(sub)
        # FIXME ca_certs=CACERTS_FILE should be used, but it didn't work for some reason.
        # Since we'll access the API locally over HTTP in future anyway, I decided to just skip validation for now
        return credentials.authorize(Http(disable_ssl_certificate_validation=True))
