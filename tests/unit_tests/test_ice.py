from unittest import mock

import pytest
from twilio.rest import Client as TwilioRestClient

from server.ice_servers.coturn import CoturnHMAC
from server.ice_servers.nts import TwilioNTS


@pytest.fixture
def coturn_hmac(coturn_hosts, coturn_keys):
    return CoturnHMAC(coturn_hosts=coturn_hosts, coturn_keys=coturn_keys)


@pytest.fixture
def twilio(twilio_sid, twilio_token):
    with mock.patch("twilio.rest.Client", mock.Mock(spec=TwilioRestClient)):
        mocked = TwilioNTS(sid=twilio_sid, token=twilio_token)
        mocked.client.tokens.create = mock.Mock(
            return_value=FakeTwilioServers()
        )
        return mocked


class FakeTwilioServers:
    def __init__(self):
        self.ice_servers = \
            {
                "urls": ["a", "b", "c"],
                "username": "d",
                "credential": "e",
                "credentialType": "f"
            }


@mock.patch("time.time", mock.Mock(return_value=1000))
def test_coturn_tokens(coturn_hmac, coturn_hosts, coturn_credentials):
    servers = coturn_hmac.server_tokens(username="faf-test", ttl=123456)
    comparison_list = []
    for coturn_host, coturn_cred in zip(coturn_hosts, coturn_credentials):
        comparison_list.append(
            {"host": coturn_host, "cred": coturn_cred}
        )

    for i in range(0, len(servers)):
        server = servers[i]
        host = comparison_list[i]["host"]
        credential = comparison_list[i]["cred"]
        assert server["credentialType"] == "token"
        assert server["urls"] == \
            [
                f"turn:{host}?transport=tcp",
                f"turn:{host}?transport=udp",
                f"stun:{host}"
            ]

        assert server["credential"] == credential
        assert server["username"] == "124456:faf-test"


@pytest.mark.asyncio
async def test_twilio_nts(twilio):
    servers = await twilio.server_tokens(ttl=123456)
    twilio.client.tokens.create.assert_called_once()
    assert servers == \
        {
            "urls": ["a", "b", "c"],
            "username": "d",
            "credential": "e",
            "credentialType": "f"
        }
