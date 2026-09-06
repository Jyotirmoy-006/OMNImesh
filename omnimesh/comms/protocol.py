from enum import Enum
from dataclasses import dataclass
from typing import Any, Dict

class MessageType(str, Enum):
    STATE_BROADCAST = "STATE_BROADCAST"
    GREEN_WAVE_REQUEST = "GREEN_WAVE_REQUEST"
    GREEN_WAVE_ACK = "GREEN_WAVE_ACK"
    CONTAINMENT_DIRECTIVE = "CONTAINMENT_DIRECTIVE"
    HEARTBEAT = "HEARTBEAT"
    ANPR_CONSENSUS_VOTE = "ANPR_CONSENSUS_VOTE"

@dataclass
class MeshMessage:
    sender_id: str
    msg_type: MessageType
    timestamp: float
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sender_id": self.sender_id,
            "msg_type": self.msg_type.value,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }
