# Log Ingestion and Analytics Backend

Minimal stack for parsing structured logs and serving analytics. The C++ ingestor now focuses purely on fast parsing and emits output to stdout (or an optional file). MongoDB access is handled from the Python FastAPI service.

## Architecture
- **C++ log ingestor**: Parses log lines with a producer/consumer worker pool and writes the parsed entries to stdout or an optional file. No database dependencies.
- **FastAPI service**: Async API backed by MongoDB (Motor + FastAPI) for querying stored logs and simple aggregations.
- **MongoDB**: Stores log documents used by the API. Ship data into MongoDB via your preferred path (API, script, or piping ingestor output into an importer).
- **Docker Compose**: Builds and runs the three services on a shared network.

## Data Flow
```
logs.txt -> C++ ingestor (parse + fan-out) -> stdout/file
                                   \
                                    -> MongoDB (via separate loader or API)
                                    -> FastAPI REST -> Client
```

## Log Format
`YYYY-MM-DD HH:MM:SS LEVEL SERVICE MESSAGE`

Example:
```
2026-01-07 14:30:45 ERROR user-service Connection timeout
```

## Project Layout
- cpp_ingestor/
  - src/main.cpp — parses logs, emits to stdout/file
  - CMakeLists.txt (unused by the current Docker build)
  - Dockerfile — single-stage g++ build
- python_api/
  - app/main.py — FastAPI + Motor analytics API
  - requirements.txt
  - Dockerfile
- logs/logs.txt — sample input
- docker-compose.yml — orchestrates mongo, API, and ingestor
- README.md

## Running
1. Ensure Docker is available.
2. From repo root: `docker compose up --build`
3. The ingestor reads `logs/logs.txt` once and streams parsed entries to its container logs (or the optional output file). The API listens on `http://localhost:8000` against MongoDB.

## API Quick Calls
- Recent logs: `curl "http://localhost:8000/logs?limit=20"`
- Filtered logs: `curl "http://localhost:8000/logs?level=ERROR&service=auth-service"`
- Counts by level: `curl http://localhost:8000/stats/levels`
- Counts by service: `curl http://localhost:8000/stats/services`

## C++ Ingestor
- Multithreaded queue: reader pushes parsed lines; workers consume and write output.
- Output destinations: stdout by default; set `OUTPUT_FILE_PATH` to append to a file.
- Environment:
  - `LOG_FILE_PATH` (default `/data/logs/logs.txt`)
  - `WORKER_COUNT` (default `4`)
  - `OUTPUT_FILE_PATH` (optional; when set, ingestor appends there)
- Built with `g++ -std=c++17` inside the image; no MongoDB libraries needed.

## FastAPI Service
- Uses `motor`/`pymongo` to talk to MongoDB at `MONGO_URI` (default `mongodb://mongo:27017/logsdb`).
- Endpoints:
  - `GET /logs` — optional `level`, `service`, `limit` (1-500)
  - `GET /stats/levels`
  - `GET /stats/services`
- Starts with `uvicorn` on port `8000` in the container.

## MongoDB
- Official `mongo:7.0` image with `mongo_data` volume.
- Populate data by piping ingestor output into a loader, using the API, or importing via `mongoimport`.

## Extending
- Swap the ingestor input by mounting a different log file or streaming logs to `/data/logs/logs.txt`.
- Wire the ingestor output into a loader that inserts into MongoDB (e.g., a small Python consumer) to make the API queries meaningful.
- Secure MongoDB with credentials and update `MONGO_URI` accordingly.
