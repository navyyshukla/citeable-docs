import resource
import time

import httpx  # noqa: F401  (imported to load it like the real app will)
import psycopg  # noqa: F401
import pydantic  # noqa: F401
import yaml  # noqa: F401
from fastapi import FastAPI

STARTED = time.time()
app = FastAPI()


@app.get("/health")
def health() -> dict:
    rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # Linux: kilobytes
    return {"ok": True, "uptime_s": round(time.time() - STARTED, 1),
            "peak_rss_mb": round(rss_kb / 1024, 1)}
