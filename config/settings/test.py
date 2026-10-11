from .base import *  # noqa: F403
from .base import SECRET_KEY

DEBUG = False
SECRET_KEY = SECRET_KEY or "test-only-insecure-key"
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
WHITENOISE_AUTOREFRESH = True  # serve from finders; no collectstatic needed in tests
