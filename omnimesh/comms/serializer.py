"""
Omni-Mesh MessagePack Binary Serializer
Encodes inter-agent state sharing payloads into compact binary MessagePack format (~80 bytes).
JSON is strictly forbidden for inter-agent state sharing to adhere to edge bandwidth constraints.
"""

from typing import Any, Dict
import msgpack

class MessageSerializer:
    """
    Binary MessagePack serializer reducing payload size from ~350B (JSON) to ~80B.
    Strictly forbids JSON for inter-agent state sharing.
    """
    def __init__(self, use_msgpack: bool = True):
        # JSON is strictly forbidden for inter-agent state sharing
        if not use_msgpack:
            raise ValueError("Forbidden: JSON serialization is strictly prohibited for inter-agent state sharing.")
        self.use_msgpack = True

    def serialize(self, data: Dict[str, Any]) -> bytes:
        """
        Encodes data dictionary into a binary MessagePack payload.
        Ensures binary encoding with use_bin_type=True.
        """
        return msgpack.packb(data, use_bin_type=True)

    def deserialize(self, payload: bytes) -> Dict[str, Any]:
        """
        Decodes a binary MessagePack payload.
        Rejects non-binary/JSON strings.
        """
        if isinstance(payload, str):
            raise ValueError("Forbidden: JSON string detected. Inter-agent state sharing strictly requires binary msgpack.")
        return msgpack.unpackb(payload, raw=False)

    def encode_agent_state(
        self,
        node_id: str,
        phase: int,
        queues: Dict[str, float],
        timestamp: float,
        threat_mode: int = 0,
        extra: Dict[str, Any] = None,
    ) -> bytes:
        """
        Encodes the agent state vector (neighbor queues, signal phase, timestamp, threat mode)
        into a binary MessagePack frame (~80 bytes).
        """
        state_payload = {
            "node_id": str(node_id),
            "phase": int(phase),
            "queues": {str(k): float(v) for k, v in queues.items()},
            "timestamp": float(timestamp),
            "threat_mode": int(threat_mode),
        }
        if extra:
            state_payload.update(extra)
        return self.serialize(state_payload)

    def decode_agent_state(self, payload: bytes) -> Dict[str, Any]:
        """Decodes binary MessagePack payload into the agent state vector."""
        return self.deserialize(payload)
