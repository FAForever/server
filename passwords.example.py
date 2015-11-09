import os

PRIVATE_KEY = None
DB_SERVER = os.getenv("DB_PORT_3306_TCP_ADDR", "localhost")
DB_PORT = int(os.getenv("DB_PORT_3306_TCP_PORT", "3306"))
DB_LOGIN = os.getenv("FAF_DB_LOGIN", "root")
DB_PASSWORD = os.getenv("DB_ENV_MYSQL_ROOT_PASSWORD", "banana")
DB_NAME = os.getenv("FAF_DB_NAME", "faf_test")

CHALLONGE_KEY = "challonge_key"
CHALLONGE_USER = "challonge_user"

VERIFICATION_SECRET_KEY = "IT'S STILL TOASTER TIME"
VERIFICATION_HASH_SECRET = "IT'S TOASTER TIME"

MAIL_ADDRESS = ""
MAIL_PASSWORD = ""

API_CLIENT_ID = "6ccaf75b-a1f3-48be-bac3-4e9ffba81eb7"
API_CLIENT_SECRET = "banana"
API_TOKEN_URI = "http://dev.faforever.com:8090/jwt/auth"
API_BASE_URL = "http://localhost:8080/jwt"
