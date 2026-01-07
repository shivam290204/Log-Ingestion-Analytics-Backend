import os
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Query, Security, HTTPException, status
from fastapi.security import APIKeyHeader
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from pydantic import BaseModel

app = FastAPI(title="Log Analytics API")

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable is not set")

API_KEY_NAME = "X-API-KEY"
API_KEY = os.getenv("API_KEY")  # Railway env se aayega

api_key_header = APIKeyHeader(
    name=API_KEY_NAME,
    auto_error=False
)

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API Key"
        )

client = AsyncIOMotorClient(MONGO_URI)
db = client["logsdb"]
collection = db["logs"]


@app.on_event("startup")
async def ensure_indexes() -> None:
    await collection.create_index("level")
    await collection.create_index("service")
    await collection.create_index("timestamp")


def serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc["_id"] = str(doc["_id"])
    return doc


@app.get("/logs", dependencies=[Security(verify_api_key)])
async def get_logs(
    level: Optional[str] = Query(None),
    service: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500)
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


class LogCreate(BaseModel):
    level: str
    service: str
    message: str
    timestamp: datetime | None = None


@app.post("/logs", dependencies=[Security(verify_api_key)])
async def add_log(log: LogCreate):
    doc = log.dict()
    if not doc.get("timestamp"):
        doc["timestamp"] = datetime.utcnow()

    await collection.insert_one(doc)
    return {"status": "inserted", "log": doc}


@app.get("/stats/levels", dependencies=[Security(verify_api_key)])
async def stats_levels():
    pipeline = [
        {"$group": {"_id": "$level", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    items: List[Dict[str, Any]] = []
    async for row in collection.aggregate(pipeline):
        items.append({"level": row.get("_id"), "count": row.get("count", 0)})
    return {"items": items}


@app.get("/stats/services", dependencies=[Security(verify_api_key)])
async def stats_services():
    pipeline = [
        {"$group": {"_id": "$service", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    items: List[Dict[str, Any]] = []
    async for row in collection.aggregate(pipeline):
        items.append({"service": row.get("_id"), "count": row.get("count", 0)})
    return {"items": items}


@app.get("/")
async def root():
    return {"status": "ok"}
