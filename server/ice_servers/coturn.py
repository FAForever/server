"""
Coturn static auth api

Creates ice_server record with temporary credentials computed from coturn static-auth-secret

http://stackoverflow.com/a/35767224
"""

import time
import hmac
import base64
from server.config import COTURN_URLS, COTURN_KEYS, TWILIO_TTL

class CoturnHMAC:
    def __init__(self, coturn_urls=None, coturn_keys=None):
        self.coturn_urls = coturn_urls or COTURN_URLS
        self.coturn_keys = coturn_keys or COTURN_KEYS

    def fetch_token(self, username='faf-user', ttl=None):
        servers = []

        ttl = ttl or TWILIO_TTL
        if ttl is not None:
            ttl = int(ttl)
        else:
            ttl = 3600*24


        # create hmac of coturn_key + timestamp:username
        timestamp = int(time.time()) + ttl
        token_name = "{}:{}".format(timestamp, username)

        for coturn_url, coturn_key in zip(self.coturn_urls, self.coturn_keys):
            secret = hmac.new(coturn_key.encode())
            secret.update(str(token_name).encode())
            auth_token = base64.b64encode(secret.digest()).decode()

            servers.append(dict(url=coturn_url,
                               username=token_name,
                               credential=auth_token))

        return servers
