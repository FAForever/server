

class DummyConnection:
    def __init__(self):
        pass

    class timer:
        def __init__(self, a):
            pass

        def __enter__(self):
            pass

        def __exit__(self, a, b, c):
            pass

    def gauge(self, a, b, delta=False):
        pass

    def incr(self, a, tags=None):
        pass

    class unit:
        def __init__(self):
            pass
