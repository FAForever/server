from asyncio import coroutine
from unittest.mock import Mock
import os


API_PRIV_KEY = """\
-----BEGIN RSA PRIVATE KEY-----
MIIBOgIBAAJBANcXbVA8c7jMb8LVSQTp7G/YAiEPi2be8k9XTqcis6QHLCw6ELh0
r8bOOkeRSUGLXja91NzJmh2Jvx/bwLhd1G0CAwEAAQJAHWPjGPKZsWel4c55AsXf
+8xdRh00pCLUo0i/w5C3UTM1fWv/8yMCSYO/th/L0/rc4kVvIOm8GOw/3zcyp6FK
dQIhAPbFBovMEDF3Tco7EiX90rVw+NgT8VoJxJACBr7R6lLjAiEA3yMQQqdpkeDA
z1zerZrzRG1Pn/OO5RCWTn3/ffIdzG8CIGUVpG7TsrZwpp72v6JsbUoB8w2gbbdy
VOCg096K4q/9AiEAkvEuRhalSPGvR18rLTw7MzahFv53fZWcxffnhnMo+HUCIH6t
GIuKi+gOWMYjXKLNRR34uxhTAvBcdZr8VBcPHSwj
-----END RSA PRIVATE KEY-----
"""

API_PUB_KEY = """\
-----BEGIN PUBLIC KEY-----
MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBANcXbVA8c7jMb8LVSQTp7G/YAiEPi2be
8k9XTqcis6QHLCw6ELh0r8bOOkeRSUGLXja91NzJmh2Jvx/bwLhd1G0CAwEAAQ==
-----END PUBLIC KEY-----
"""
os.environ['API_JWT_PUBLIC_KEY'] = API_PUB_KEY


def CoroMock(**kwargs) -> Mock:
    coro = Mock(name="CoroutineResult", **kwargs)
    corofunc = Mock(name="CoroutineFunction", side_effect=coroutine(coro))
    corofunc.coro = coro
    return corofunc
