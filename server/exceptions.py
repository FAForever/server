"""
Common exception definitions
"""

import humanize

from server.timing import datetime_now

BAN_NOTICE_I18N_KEY = "notice.ban"
BAN_APPEAL_EMAIL = "moderation@faforever.com"


class ClientError(Exception):
    """
    Represents a protocol violation by the client.

    If recoverable is False, it is expected that the connection be terminated
    immediately.
    """

    def __init__(self, message, recoverable=True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message
        self.recoverable = recoverable


class BanError(Exception):
    """
    Signals that an operation could not be completed because the user is banned.
    """

    def __init__(self, ban_expiry, ban_reason, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ban_expiry = ban_expiry
        self.ban_reason = ban_reason

    def localization(self):
        return {
            "i18n_key": BAN_NOTICE_I18N_KEY,
            "i18n_args": {
                "duration": self._ban_duration_text(),
                "reason": self.ban_reason,
                "appeal_email": BAN_APPEAL_EMAIL
            }
        }

    def message(self):
        data = self.localization()["i18n_args"]
        return (
            f"You are banned from FAF {data['duration']}. <br>"
            f"Reason: <br>{data['reason']}<br><br>"
            "<i>If you would like to appeal this ban, please send an email to: "
            f"{data['appeal_email']}</i>"
        )

    def _ban_duration_text(self):
        ban_duration = self.ban_expiry - datetime_now()
        if ban_duration.days > 365 * 100:
            return "forever"
        humanized_ban_duration = humanize.precisedelta(
            ban_duration,
            minimum_unit="hours"
        )
        return f"for {humanized_ban_duration}"


class AuthenticationError(Exception):
    """
    The operation failed to authenticate.
    """

    def __init__(self, message, method, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message
        self.method = method


class DisabledError(Exception):
    """
    The operation is disabled due to an impending server shutdown.
    """
