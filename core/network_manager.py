import time
from typing import Dict, Any, List

class LocalNetworkManager:
    def __init__(self, hub_id: str = "HUB_SILCHAR_01", max_sdcch_capacity: int = 8, silent_timeout_sec: float = 300.0):
        self.hub_id = hub_id
        self.max_sdcch = max_sdcch_capacity
        self.silent_timeout = silent_timeout_sec
        self.sessions: Dict[int, Dict[str, Any]] = {}
        self.next_local_id = 1

    def handle_attach_request(self, device_hash: int) -> Dict[str, Any]:
        active_count = len(self.sessions)
        
        if active_count >= self.max_sdcch:
            target_hub = f"HUB_NEIGHBOR_{int(self.hub_id.split('_')[-1]) + 1}"
            return {
                "action": "HANDOVER_REDIRECT",
                "target_hub": target_hub,
                "reason": "SDCCH_CAPACITY_EXCEEDED",
                "load": f"{active_count}/{self.max_sdcch}"
            }

        if device_hash not in self.sessions:
            assigned_id = self.next_local_id
            self.sessions[device_hash] = {
                "local_id": assigned_id,
                "last_seen": time.time(),
                "status": "ACTIVE"
            }
            self.next_local_id = (self.next_local_id % 254) + 1
        else:
            self.sessions[device_hash]["last_seen"] = time.time()
            assigned_id = self.sessions[device_hash]["local_id"]

        return {
            "action": "ATTACH_SUCCESS",
            "local_id": assigned_id,
            "hub_id": self.hub_id,
            "load": f"{len(self.sessions)}/{self.max_sdcch}"
        }

    def check_silent_devices(self) -> List[Dict[str, Any]]:
        now = time.time()
        silent_list = []
        for dev_hash, session in self.sessions.items():
            if now - session["last_seen"] > self.silent_timeout and session["status"] != "SILENT":
                session["status"] = "SILENT"
                silent_list.append({
                    "device_hash": dev_hash,
                    "local_id": session["local_id"],
                    "silent_duration_sec": round(now - session["last_seen"], 1)
                })
        return silent_list
