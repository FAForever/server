import json
from functools import partial
import asyncio
from httplib2 import Http
from oauth2client.service_account import ServiceAccountCredentials
from passwords import API_TOKEN_URI, API_BASE_URL


class ApiAccessor:
    def __init__(self):
        with open("faf-server.pem", "rb") as f:
            self.private_key = f.read()

    async def api_get(self, path, player_id):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, partial(self.http(player_id).request, API_BASE_URL + path, "GET"))
        return result

    async def api_post(self, path, player_id, data=None, headers=None):
        headers = headers or {'Content-type': 'application/json'}
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(self.http(player_id).request, API_BASE_URL + path, "POST", headers=headers, body=json.dumps(data)))

        return result

    def http(self, sub=None):
        credentials = ServiceAccountCredentials.from_p12_keyfile(
            'faf-server',
            'faf-server.pem',
            scopes='write_achievements write_events'
        )
        return credentials.authorize(Http())
