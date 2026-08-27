import time
import math
from collections import deque
from typing import Dict, Tuple, Optional, Any

class TokenBucketRateLimiter:
    def __init__(self, capacity: int = 5, refill_rate: float = 1.0 / 12.0):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.buckets: Dict[int, Dict[str, float]] = {}

    def allow_request(self, device_hash: int, high_load_active: bool = False) -> Tuple[bool, float]:
        now = time.time()
        current_cap = 2 if high_load_active else self.capacity
        
        if device_hash not in self.buckets:
            self.buckets[device_hash] = {"tokens": current_cap - 1, "last_refill": now}
            return True, current_cap - 1

        state = self.buckets[device_hash]
        elapsed = now - state["last_refill"]
        state["tokens"] = min(current_cap, state["tokens"] + elapsed * self.refill_rate)
        state["last_refill"] = now

        if state["tokens"] >= 1.0:
            state["tokens"] -= 1.0
            return True, state["tokens"]
        return False, state["tokens"]

class NetworkTrafficManager:
    def __init__(self, grid_cell_meters: float = 100.0, heat_threshold_msgs: int = 4, heat_window_sec: float = 180.0):
        self.rate_limiter = TokenBucketRateLimiter()
        self.grid_cell_size = grid_cell_meters
        self.heat_threshold = heat_threshold_msgs
        self.heat_window = heat_window_sec

        self.clusters: Dict[Tuple[str, int], Dict[str, Any]] = {}
        self.cell_message_history: Dict[str, deque] = {}

        self.p0_queue: deque = deque()
        self.p1_queue: deque = deque()
        self.p2_queue: deque = deque()

    def _coord_to_cell_id(self, lat: float, lon: float) -> str:
        lat_step = self.grid_cell_size / 111000.0
        lon_step = self.grid_cell_size / (111000.0 * math.cos(math.radians(lat)))
        grid_x = int(lat / lat_step)
        grid_y = int(lon / lon_step)
        return f"CELL_{grid_x}_{grid_y}"

    def _is_in_declared_zone(self, lat: float, lon: float, zone_bounds: Dict[str, float]) -> bool:
        return (zone_bounds["min_lat"] <= lat <= zone_bounds["max_lat"] and
                zone_bounds["min_lon"] <= lon <= zone_bounds["max_lon"])

    def ingest_packet(self, packet: Dict[str, Any], zone_bounds: Dict[str, float], sdcch_overloaded: bool = False) -> Dict[str, Any]:
        dev_hash = packet["device_hash"]
        
        allowed, rem_tokens = self.rate_limiter.allow_request(dev_hash, high_load_active=sdcch_overloaded)
        if not allowed:
            return {"status": "RATE_LIMITED_QUEUED", "device_hash": dev_hash, "action": "SILENT_QUEUED"}

        cell_id = self._coord_to_cell_id(packet["lat"], packet["lon"])
        category = packet["need"]
        now = time.time()

        if cell_id not in self.cell_message_history:
            self.cell_message_history[cell_id] = deque()
        hist = self.cell_message_history[cell_id]
        hist.append(now)
        while hist and now - hist[0] > self.heat_window:
            hist.popleft()
        
        is_heating_up = len(hist) >= self.heat_threshold

        cluster_key = (cell_id, category)
        in_zone = self._is_in_declared_zone(packet["lat"], packet["lon"], zone_bounds)
        is_critical = (packet["severity"] == 3)

        if cluster_key in self.clusters:
            record = self.clusters[cluster_key]
            record["headcount"] = max(record["headcount"], packet["victim_count"])
            record["last_updated"] = now
            if dev_hash not in record["device_list"]:
                record["device_list"].append(dev_hash)
            return {"status": "CLUSTERED_AGGREGATED", "cell_id": cell_id, "total_devices": len(record["device_list"])}
        else:
            record = {
                "cell_id": cell_id,
                "lat": packet["lat"],
                "lon": packet["lon"],
                "category": category,
                "severity": packet["severity"],
                "headcount": packet["victim_count"],
                "first_seen": now,
                "last_updated": now,
                "device_list": [dev_hash],
                "landmark": packet["landmark"]
            }
            self.clusters[cluster_key] = record

            if in_zone and is_critical:
                self.p0_queue.append(record)
                tier = "P0"
            elif (in_zone and not is_critical) or is_heating_up:
                self.p1_queue.append(record)
                tier = "P1 (Promoted)" if is_heating_up and not in_zone else "P1"
            else:
                self.p2_queue.append(record)
                tier = "P2"

            return {"status": "NEW_CLUSTER_ENQUEUED", "tier": tier, "cell_id": cell_id}

    def schedule_next_dispatch(self) -> Optional[Dict[str, Any]]:
        if self.p0_queue:
            return self.p0_queue.popleft()
        if self.p1_queue:
            return self.p1_queue.popleft()
        if self.p2_queue:
            return self.p2_queue.popleft()
        return None
