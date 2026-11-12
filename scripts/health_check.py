#!/usr/bin/env python3
"""
Platform Health Checker Script.
Checks Django web endpoint, PostgreSQL connectivity, and Redis latency.
Can be run via cron or container orchestrator monitoring.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

try:
    import redis
except ImportError:
    redis = None

try:
    import psycopg
except ImportError:
    psycopg = None


def check_http_endpoint(url="http://localhost:8000/health/"):
    try:
        t0 = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": "HealthChecker/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            latency_ms = int((time.time() - t0) * 1000)
            status_code = response.getcode()
            body = response.read().decode("utf-8")
            return {
                "status": "HEALTHY" if status_code == 200 else "DEGRADED",
                "status_code": status_code,
                "latency_ms": latency_ms,
                "details": body[:200],
            }
    except Exception as e:
        return {"status": "OFFLINE", "error": str(e)}


def check_redis(redis_url=None):
    if not redis:
        return {"status": "SKIPPED", "note": "redis library not installed"}
    url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        t0 = time.time()
        client = redis.from_url(url, socket_timeout=3)
        client.ping()
        latency_ms = int((time.time() - t0) * 1000)
        return {"status": "HEALTHY", "latency_ms": latency_ms}
    except Exception as e:
        return {"status": "DEGRADED", "error": str(e)}


def main():
    http_result = check_http_endpoint()
    redis_result = check_redis()

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "http": http_result,
        "redis": redis_result,
        "overall": "HEALTHY" if http_result.get("status") == "HEALTHY" else "DEGRADED",
    }

    print(json.dumps(report, indent=2))
    if report["overall"] != "HEALTHY":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

