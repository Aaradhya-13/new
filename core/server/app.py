import asyncio
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from packet.protocol_37b import Protocol37B
from core.network_manager import LocalNetworkManager
from core.traffic_manager import NetworkTrafficManager
from core.triage_engine import TriageEngine
from core.sync_layer import HubSyncStore

app = FastAPI(title="2G Disaster Hub Node & Traffic Commander")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

network_mgr = LocalNetworkManager(hub_id="HUB_ASSAM_01", max_sdcch_capacity=8)
traffic_mgr = NetworkTrafficManager()
sync_store = HubSyncStore("hub_main.db")

DECLARED_ZONE = {"min_lat": 24.810, "max_lat": 24.850, "min_lon": 92.770, "max_lon": 92.820}

class Broadcaster:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, data: dict):
        for conn in self.connections:
            try:
                await conn.send_json(data)
            except Exception:
                pass

broadcaster = Broadcaster()

class DistressRequest(BaseModel):
    lat: float
    lon: float
    severity: int
    need: int
    count: int
    seq: int
    imei: int
    landmark: str

@app.post("/api/attach")
async def sdcch_attach(imei: int):
    return network_mgr.handle_attach_request(imei)

@app.post("/api/send-sos")
async def receive_sos(req: DistressRequest):
    attach_info = network_mgr.handle_attach_request(req.imei)
    local_id = attach_info.get("local_id", 1)
    sdcch_overloaded = (attach_info.get("action") == "HANDOVER_REDIRECT")

    # 1. 37-Byte Binary Pack[cite: 1]
    packed_bytes = Protocol37B.pack(
        lat=req.lat, lon=req.lon, local_id=local_id,
        severity=req.severity, need=req.need, count=req.count,
        seq=req.seq, device_hash=req.imei, landmark=req.landmark
    )

    # 2. Unpack & Verify CRC[cite: 1]
    parsed_pkt = Protocol37B.unpack(packed_bytes)

    # 3. Traffic Manager Ingestion
    ingest_result = traffic_mgr.ingest_packet(parsed_pkt, DECLARED_ZONE, sdcch_overloaded)

    # 4. Dispatch Scheduling
    dispatch_item = traffic_mgr.schedule_next_dispatch()
    if dispatch_item:
        dispatch_item["triage_score"] = TriageEngine.calculate_score(dispatch_item)
        sync_store.upsert_cluster(dispatch_item)

        await broadcaster.broadcast({
            "type": "NEW_TRIAGE_CLUSTER",
            "cluster": dispatch_item,
            "raw_hex": parsed_pkt["hex_dump"],
            "sdcch_load": f"{len(network_mgr.sessions)}/{network_mgr.max_sdcch}",
            "ingest_meta": ingest_result
        })

    return {
        "status": "PROCESSED",
        "ack_packet": Protocol37B.pack_ack(req.imei, 1).hex(),
        "ingest_result": ingest_result
    }

@app.post("/api/mule-sync")
async def physical_carrier_sync(last_sync: float):
    delta = sync_store.get_delta_payload(last_sync)
    return {"synced_count": len(delta), "records": delta}

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await broadcaster.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        broadcaster.disconnect(ws)
