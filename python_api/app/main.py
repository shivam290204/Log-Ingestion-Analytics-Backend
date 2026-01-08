import os
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import (
    FastAPI,
    Query,
    Security,
    HTTPException,
    status,
    Request,
    Depends
)
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse

from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

# ---------- RATE LIMITING ----------
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Log Analytics API")
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


# 🔹 Custom error message for rate limit
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Try again later."}
    )


# ---------- ENV VARIABLES ----------
MONGO_URI = os.getenv("MONGO_URI")
API_KEY = os.getenv("API_KEY")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable is not set")


# ---------- API KEY SECURITY ----------
API_KEY_NAME = "X-API-KEY"

api_key_header = APIKeyHeader(
    name=API_KEY_NAME,
    auto_error=False
)


async def verify_api_key(
    request: Request,
    api_key: str = Security(api_key_header)
) -> str:
    if not API_KEY:
        raise HTTPException(
            status_code=500,
            detail="API_KEY not configured on server"
        )

    # Try header first, then query parameter (for browser testing)
    key = api_key or request.query_params.get("api_key")
    
    if key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )

    return key


# ---------- DATABASE ----------
client = AsyncIOMotorClient(MONGO_URI)
db = client["logsdb"]
collection = db["logs"]


@app.on_event("startup")
async def ensure_indexes():
    await collection.create_index("level")
    await collection.create_index("service")
    await collection.create_index("timestamp")


# ---------- HELPERS ----------
def serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc["_id"] = str(doc["_id"])
    return doc


# ---------- SCHEMAS ----------
class LogCreate(BaseModel):
    level: str
    service: str
    message: str
    timestamp: Optional[datetime] = None


# ---------- ROUTES ----------

@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/logs")
@limiter.limit("20/minute")
async def get_logs(
    request: Request,
    level: Optional[str] = Query(None),
    service: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    _: str = Depends(verify_api_key)
):
    query: Dict[str, Any] = {}

    if level:
        query["level"] = level
    if service:
        query["service"] = service

    cursor = collection.find(query).sort("timestamp", -1).limit(limit)

    items: List[Dict[str, Any]] = []
    async for doc in cursor:
        items.append(serialize(doc))

    return {"count": len(items), "items": items}


@app.post("/logs")
@limiter.limit("10/minute")
async def add_log(
    request: Request,
    log: LogCreate,
    _: str = Depends(verify_api_key)
):
    doc = log.model_dump()

    if not doc.get("timestamp"):
        doc["timestamp"] = datetime.utcnow()

    await collection.insert_one(doc)
    return {"status": "inserted", "log": doc}


@app.get("/stats/levels")
async def stats_levels(_: str = Depends(verify_api_key)):
    pipeline = [
        {"$group": {"_id": "$level", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]

    items: List[Dict[str, Any]] = []
    async for row in collection.aggregate(pipeline):
        items.append({
            "level": row["_id"],
            "count": row["count"]
        })

    return {"items": items}


@app.get("/stats/services")
async def stats_services(_: str = Depends(verify_api_key)):
    pipeline = [
        {"$group": {"_id": "$service", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]

    items: List[Dict[str, Any]] = []
    async for row in collection.aggregate(pipeline):
        items.append({
            "service": row["_id"],
            "count": row["count"]
        })

    return {"items": items}
