import time
from typing import Dict, Any

class TriageEngine:
    SEVERITY_WEIGHTS = {3: 120.0, 2: 70.0, 1: 30.0, 0: 10.0}
    NEED_WEIGHTS = {2: 25.0, 1: 15.0, 3: 5.0, 0: 0.0} # 2=Medical, 1=Boat, 3=Food[cite: 1]

    @classmethod
    def calculate_score(cls, item: Dict[str, Any], boat_lat: float = 24.825, boat_lon: float = 92.795) -> float:
        sev_score = cls.SEVERITY_WEIGHTS.get(item.get("severity", 1), 10.0)
        need_score = cls.NEED_WEIGHTS.get(item.get("category", 1), 0.0)
        headcount_score = item.get("headcount", 1) * 6.0
        
        wait_minutes = (time.time() - item.get("first_seen", time.time())) / 60.0
        wait_score = min(wait_minutes * 1.2, 40.0)
        
        dist_km = (abs(item.get("lat", boat_lat) - boat_lat) + abs(item.get("lon", boat_lon) - boat_lon)) * 111.0
        dist_penalty = dist_km * 2.5
        
        final_score = sev_score + need_score + headcount_score + wait_score - dist_penalty
        return round(max(final_score, 1.0), 2)
