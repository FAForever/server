import asyncio

class UdpProxy:
    pass

proxy_range = range(30352, 66500)

# Map from port number -> proxy process
proxy_processes = {}

@asyncio.coroutine
def try_start(remote_addr):
    for i in proxy_range:
        if proxy_processes[i]:
            continue
        proc = yield from asyncio.create_subprocess_exec('socat',
                                                         'UDP-RECV:{}'.format(i),
                                                         'UDP:{}'.format(remote_addr),
                                                         '-T90')
        try:
            yield from asyncio.wait_for(proc.stderr.readline(), 0.5)
            # If the above wait _doesn't_ time out, socat is listening
            proc.kill()
            continue

        except asyncio.TimeoutError:
            return proc

@asyncio.coroutine
def create(addr1, addr2):
    """
    Spawn a pair of socat processes to facilitate UDP communication between given addresses
    :return:
    """
    peer_1_proxy = asyncio.create_subprocess_exec('socat',
                                                  'UDP-RECV:{}'.format(addr1),
                                                  'UDP:{}'.format(addr2))
    peer_2_proxy = asyncio.create_subprocess_exec('socat')
