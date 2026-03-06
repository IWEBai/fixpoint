from __future__ import annotations

from functools import lru_cache

import redis
from rq import Queue

from railo_cloud.config import get_settings


@lru_cache(maxsize=1)
def get_redis_connection():
    settings = get_settings()
    return redis.from_url(settings.redis_url)


@lru_cache(maxsize=1)
def get_queue() -> Queue:
    settings = get_settings()
    conn = get_redis_connection()
    return Queue(settings.rq_queue, connection=conn, default_timeout=900)
