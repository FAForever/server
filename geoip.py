# List of country codes (indexed by GeoIP country ID number)
countries = (
    '',   'AP', 'EU', 'AD', 'AE', 'AF', 'AG', 'AI', 'AL', 'AM', 'AN', 'AO', 'AQ',
    'AR', 'AS', 'AT', 'AU', 'AW', 'AZ', 'BA', 'BB', 'BD', 'BE', 'BF', 'BG', 'BH',
    'BI', 'BJ', 'BM', 'BN', 'BO', 'BR', 'BS', 'BT', 'BV', 'BW', 'BY', 'BZ', 'CA',
    'CC', 'CD', 'CF', 'CG', 'CH', 'CI', 'CK', 'CL', 'CM', 'CN', 'CO', 'CR', 'CU',
    'CV', 'CX', 'CY', 'CZ', 'DE', 'DJ', 'DK', 'DM', 'DO', 'DZ', 'EC', 'EE', 'EG',
    'EH', 'ER', 'ES', 'ET', 'FI', 'FJ', 'FK', 'FM', 'FO', 'FR', 'FX', 'GA', 'GB',
    'GD', 'GE', 'GF', 'GH', 'GI', 'GL', 'GM', 'GN', 'GP', 'GQ', 'GR', 'GS', 'GT',
    'GU', 'GW', 'GY', 'HK', 'HM', 'HN', 'HR', 'HT', 'HU', 'ID', 'IE', 'IL', 'IN',
    'IO', 'IQ', 'IR', 'IS', 'IT', 'JM', 'JO', 'JP', 'KE', 'KG', 'KH', 'KI', 'KM',
    'KN', 'KP', 'KR', 'KW', 'KY', 'KZ', 'LA', 'LB', 'LC', 'LI', 'LK', 'LR', 'LS',
    'LT', 'LU', 'LV', 'LY', 'MA', 'MC', 'MD', 'MG', 'MH', 'MK', 'ML', 'MM', 'MN',
    'MO', 'MP', 'MQ', 'MR', 'MS', 'MT', 'MU', 'MV', 'MW', 'MX', 'MY', 'MZ', 'NA',
    'NC', 'NE', 'NF', 'NG', 'NI', 'NL', 'NO', 'NP', 'NR', 'NU', 'NZ', 'OM', 'PA',
    'PE', 'PF', 'PG', 'PH', 'PK', 'PL', 'PM', 'PN', 'PR', 'PS', 'PT', 'PW', 'PY',
    'QA', 'RE', 'RO', 'RU', 'RW', 'SA', 'SB', 'SC', 'SD', 'SE', 'SG', 'SH', 'SI',
    'SJ', 'SK', 'SL', 'SM', 'SN', 'SO', 'SR', 'ST', 'SV', 'SY', 'SZ', 'TC', 'TD',
    'TF', 'TG', 'TH', 'TJ', 'TK', 'TM', 'TN', 'TO', 'TL', 'TR', 'TT', 'TV', 'TW',
    'TZ', 'UA', 'UG', 'UM', 'US', 'UY', 'UZ', 'VA', 'VC', 'VE', 'VG', 'VI', 'VN',
    'VU', 'WF', 'WS', 'YE', 'YT', 'RS', 'ZA', 'ZM', 'ME', 'ZW', 'A1', 'A2', 'O1',
    'AX', 'GG', 'IM', 'JE', 'BL', 'MF')

def iptonum(ip):
    """Convert IP address string to 32-bit integer, or return None if IP is bad.

    >>> iptonum('0.0.0.0')
    0
    >>> hex(iptonum('127.0.0.1'))
    '0x7f000001'
    >>> hex(iptonum('255.255.255.255'))
    '0xffffffffL'
    >>> iptonum('127.0.0.256')
    >>> iptonum('1.2.3')
    >>> iptonum('a.s.d.f')
    >>> iptonum('1.2.3.-4')
    >>> iptonum('')
    """
    segments = ip.split('.')
    if len(segments) != 4:
        return None
    num = 0
    for segment in segments:
        try:
            segment = int(segment)
        except ValueError:
            return None
        if segment < 0 or segment > 255:
            return None
        num = num << 8 | segment
    return num

class DatabaseError(Exception):
    pass

class GeoIP(object):
    """Wraps GeoIP country database lookup into a class."""

    _record_length = 3
    _country_start = 16776960

    def __init__(self, dbname='GeoIP.dat'):
        """Init GeoIP instance with given GeoIP country database file."""
        self._dbfile = open(dbname, 'rb')

    def country(self, ip):
        """Lookup IP address string and turn it into a two-letter country code
        like 'NZ', or return empty string if unknown.

        >>> g = GeoIP()
        >>> g.country('64.233.161.99')
        'US'
        >>> g.country('202.21.128.102')
        'NZ'
        >>> g.country('asdf')
        ''
        >>> g.country('127.0.0.1')
        ''
        """
        ipnum = iptonum(ip)
        if ipnum is None:
            return ''
        return countries[self._country_id(ipnum)]

    def _country_id(self, ipnum):
        """Look up and return country ID of given 32-bit IP address."""
        # Search algorithm from: http://code.google.com/p/pygeoip/
        offset = 0
        for depth in range(31, -1, -1):
            self._dbfile.seek(offset * 2 * self._record_length)
            data = self._dbfile.read(2 * self._record_length)
            x = [0, 0]
            for i in range(2):
                for j in range(self._record_length):
                    x[i] += ord(data[self._record_length * i + j]) << (j * 8)
            i = 1 if ipnum & (1 << depth) else 0
            if x[i] >= self._country_start:
                return x[i] - self._country_start
            offset = x[i]
        raise DatabaseError('GeoIP database corrupt: offset=%s' % offset)

def country(ip, dbname='GeoIP.dat'):
    """Helper function that creates a GeoIP instance and calls country()."""
    return GeoIP(dbname).country(ip)