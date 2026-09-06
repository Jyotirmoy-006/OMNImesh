import json
from typing import Any, Dict
try:
    import msgpack
    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False

class MessageSerializer:
    """
    Binary MessagePack serializer reducing payload size from ~350B to ~80B.
    Falls back gracefully to JSON if msgpack is unavailable.
    """
    def __init__(self, use_msgpack: bool = True):
        self.use_msgpack = use_msgpack and HAS_MSGPACK

    def serialize(self, data: Dict[str, Any]) -> bytes:
        if self.use_msgpack:
            return msgpack.packb(data, use_bin_type=True)
        return json.dumps(data).encode("utf-8")

    def deserialize(self, payload: bytes) -> Dict[str, Any]:
        if self.use_msgpack:
            return msgpack.unpackb(payload, raw=False)
        return json.loads(payload.decode("utf-8"))
