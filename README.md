# CrowdShield — 2G Small Area Network & Tactical Disaster Hub

An offline-first, closed-loop disaster dispatch system engineered for complete cellular and internet blackouts.

## Architecture
- **packet/**: 37-byte fixed binary serialization with CRC-16 integrity verification.
- **core/**: SDCCH channel allocation, token-bucket rate limiting, 100m grid clustering, multi-tier P0-P2 priority queues, and delay-tolerant SQLite delta sync.
- **server/**: FastAPI hub node with real-time WebSocket broadcasting.
- **dashboard/**: Tactical Leaflet-based SAR flood command console and *112# USSD simulator.

## Run Instructions
```bash
pip install -r requirements.txt
python -m uvicorn server.app:app --reload --port 8000
