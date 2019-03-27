"""
Coturn static auth api

Creates ice_server record with temporary credentials computed from coturn static-auth-secret

http://stackoverflow.com/a/35767224
"""

import time
import hmac
import base64
from hashlib import sha1
from server.config import COTURN_HOSTS, COTURN_KEYS, TWILIO_TTL

class CoturnHMAC:
    def __init__(self, coturn_hosts=None, coturn_keys=None):
        self.coturn_hosts = coturn_hosts or COTURN_HOSTS
        self.coturn_keys = coturn_keys or COTURN_KEYS

    def fetch_token(self, username='faf-user', ttl=TWILIO_TTL):
        servers = []

        if ttl is not None:
            ttl = int(ttl)
        else:
            ttl = 3600*24

        # See https://github.com/coturn/coturn/wiki/turnserver#turn-rest-api
        # create hmac of coturn_key + timestamp:username
        timestamp = int(time.time()) + ttl
        token_name = "{}:{}".format(timestamp, username)

        for coturn_host, coturn_key in zip(self.coturn_hosts, self.coturn_keys):
            secret = hmac.new(coturn_key.encode(), str(token_name).encode(), sha1)
            auth_token = base64.b64encode(secret.digest()).decode()

            servers.append(dict(urls=["turn:{}?transport=tcp".format(coturn_host),
                                      "turn:{}?transport=udp".format(coturn_host),
                                      "stun:{}".format(coturn_host)],
                                username=token_name,
                                credential=auth_token,
                                credentialType="token"))

        return servers
