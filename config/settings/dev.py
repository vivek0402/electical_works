from .base import *  # noqa: F403
from .base import SECRET_KEY, env

DEBUG = env.bool("DEBUG", default=True)
SECRET_KEY = SECRET_KEY or "dev-only-insecure-key-do-not-use-in-prod"
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "0.0.0.0"])
