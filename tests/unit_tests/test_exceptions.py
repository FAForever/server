from datetime import datetime, timedelta, timezone

from server.exceptions import BanError

BAN_REASON = "Test ban reason"


def make_ban_error(expiry):
    return BanError(expiry, BAN_REASON)


class TestBanErrorNotice:
    def test_notice_keeps_legacy_fields(self):
        expiry = datetime(2030, 1, 1, tzinfo=timezone.utc)
        error = make_ban_error(expiry)

        notice = error.notice()

        assert notice["command"] == "notice"
        assert notice["style"] == "error"
        assert notice["text"] == error.message()

    def test_notice_includes_i18n_key_and_args(self):
        expiry = datetime(2030, 1, 1, tzinfo=timezone.utc)

        notice = make_ban_error(expiry).notice()

        assert notice["i18n_key"] == "login.error.banned"
        assert notice["i18n_args"] == [
            "2030-01-01T00:00:00+00:00",
            BAN_REASON
        ]

    def test_notice_expires_at_is_iso_utc_timestamp(self):
        expiry = datetime.now(timezone.utc) + timedelta(days=30)

        notice = make_ban_error(expiry).notice()

        assert notice["expires_at"] == expiry.isoformat()
        assert datetime.fromisoformat(notice["expires_at"]) == expiry
        # The first i18n argument is the same timestamp, as the
        # `login.error.banned` translation expects the expiry first and
        # the ban reason second.
        assert notice["i18n_args"][0] == notice["expires_at"]
        assert notice["i18n_args"][1] == BAN_REASON

    def test_notice_for_permanent_ban(self):
        expiry = datetime.now(timezone.utc) + timedelta(days=365 * 1000)

        notice = make_ban_error(expiry).notice()

        assert "forever" in notice["text"]
        assert notice["expires_at"] == expiry.isoformat()
        assert notice["i18n_key"] == "login.error.banned"
        assert notice["i18n_args"] == [expiry.isoformat(), BAN_REASON]
