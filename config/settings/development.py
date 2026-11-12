"""
Development settings for Indian Stock Market Research & Intelligence Platform.
"""
from .base import *

DEBUG = True

# Database: Uses DATABASE_URL if configured; supports PostgreSQL or SQLite fallback
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}

# Redis cache if reachable, otherwise fall back to LocMemCache
try:
    import redis
    redis_client = redis.from_url(env("REDIS_URL"), socket_connect_timeout=1)
    redis_client.ping()
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": env("REDIS_URL"),
        }
    }
except Exception:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "dev-cache",
        }
    }

# Email backend for development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

