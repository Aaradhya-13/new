import struct
import time
import zlib
from typing import Dict, Any

class Protocol37B:
    """
    37-Byte Fixed Binary Protocol:
    Lat(4B) + Lon(4B) + LocalID(1B) + MetaBitfield(1B) + Seq(2B) + 
    Timestamp(4B) + DeviceHash(8B) + CRC16(2B) + LandmarkGrid(11B) = 37 Bytes[cite: 1]
    """
    STRUCT_FORMAT = '<2f2BHIQH11s'
    RAW_BODY_FORMAT = '<2f2BHIQ11s'

    @classmethod
    def pack(cls, lat: float, lon: float, local_id: int, severity: int, need: int, 
             count: int, seq: int, device_hash: int, landmark: str = "SEC_GRID_01") -> bytes:
        packed_meta = ((severity & 0x03) << 6) | ((need & 0x03) << 4) | (count & 0x0F)
        ts = int(time.time())
        landmark_bytes = landmark.encode('ascii')[:11].ljust(11, b'\x00')

        raw_body = struct.pack(cls.RAW_BODY_FORMAT, lat, lon, local_id, packed_meta, seq, ts, device_hash, landmark_bytes)
        checksum = zlib.crc32(raw_body) & 0xFFFF

        return struct.pack(cls.STRUCT_FORMAT, lat, lon, local_id, packed_meta, seq, ts, device_hash, checksum, landmark_bytes)

    @classmethod
    def unpack(cls, payload: bytes) -> Dict[str, Any]:
        if len(payload) != 37:
            raise ValueError(f"Corrupted packet: Expected 37 bytes, got {len(payload)}")

        lat, lon, local_id, packed_meta, seq, ts, device_hash, checksum, landmark_bytes = struct.unpack(cls.STRUCT_FORMAT, payload)
        
        raw_body = struct.pack(cls.RAW_BODY_FORMAT, lat, lon, local_id, packed_meta, seq, ts, device_hash, landmark_bytes)
        calculated_crc = zlib.crc32(raw_body) & 0xFFFF
        
        if calculated_crc != checksum:
            raise ValueError(f"CRC-16 mismatch: calculated {calculated_crc}, received {checksum}")

        return {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "local_id": local_id,
            "severity": (packed_meta >> 6) & 0x03, # 3=P0 Critical, 2=P1 High, 1=Med, 0=Low
            "need": (packed_meta >> 4) & 0x03,     # 1=Boat, 2=Medical, 3=Ration[cite: 1]
            "victim_count": packed_meta & 0x0F,
            "seq": seq,
            "timestamp": ts,
            "device_hash": device_hash,
            "landmark": landmark_bytes.decode('ascii').rstrip('\x00'),
            "hex_dump": payload.hex().upper()
        }

    @staticmethod
    def pack_ack(device_hash: int, status_code: int) -> bytes:
        return struct.pack('<QB', device_hash, status_code)
