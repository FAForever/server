from datetime import datetime, timedelta

CONN_ATTEMPTS = 10
CONN_TIME = timedelta(minutes=1)

class ConnectionThrottler:
    """Simple Connection throttler to limit bruteforce attacks

    Records the number of connection attempts from remote hosts in a specified
    timespan, allowing to deny connections if there have been too many
    """
    def __init__(self):
        self.conn_attempts = {}
        self.ts = datetime.now()

    def attempt(self, ip):
        """Record a connection attempt

        Returns True if number of recorded attempts smaller than allowed number,
        False otherwise
        """
        # Check for time window rollover
        now = datetime.now()
        if now - self.ts > CONN_TIME:
            # Reset everything if we're rolled over
            self.conn_attempts = {}
            self.ts = now

        self.conn_attempts[ip] = self.conn_attempts.get(ip, 0) + 1

        return self.conn_attempts[ip] <= CONN_ATTEMPTS
