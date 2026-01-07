import os
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Query, Header, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from pydantic import BaseModel

app = FastAPI(title="Log Analytics API")

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable is not set")

API_KEY = os.getenv("LOG_API_KEY")

def verify_api_key(x_api_key: str = Header(...)):
    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

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


@app.get("/logs")
async def get_logs(
    level: Optional[str] = Query(None),
    service: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    _: None = Depends(verify_api_key)
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


@app.post("/logs")
async def add_log(
    log: LogCreate,
    _: None = Depends(verify_api_key)
):
    doc = log.dict()
    if not doc.get("timestamp"):
        doc["timestamp"] = datetime.utcnow()

    await collection.insert_one(doc)
    return {"status": "inserted", "log": doc}


@app.get("/stats/levels")
async def stats_levels(_: None = Depends(verify_api_key)):
    pipeline = [
        {"$group": {"_id": "$level", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    items: List[Dict[str, Any]] = []
    async for row in collection.aggregate(pipeline):
        items.append({"level": row.get("_id"), "count": row.get("count", 0)})
    return {"items": items}


@app.get("/stats/services")
async def stats_services(_: None = Depends(verify_api_key)):
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
