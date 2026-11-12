"""
Production settings for Indian Stock Market Research & Intelligence Platform.
"""
from .base import *

DEBUG = False

ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ValueError("DJANGO_ALLOWED_HOSTS must be set in production")

# Production strictly enforces PostgreSQL
DATABASES = {
    "default": env.db("DATABASE_URL")
}
if "sqlite" in DATABASES["default"]["ENGINE"]:
    raise ValueError("Production requires PostgreSQL, SQLite is not allowed")

# Security headers & SSL
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Redis Cache in production
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
    }
}

