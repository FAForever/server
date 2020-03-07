class ClientError(Exception):
    """
    Represents a ClientError

    If recoverable is False, it is expected that the
    connection be terminated immediately.
    """
    def __init__(self, message, recoverable=True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message
        self.recoverable = recoverable


class AuthenticationError(Exception):
    def __init__(self, message, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message
