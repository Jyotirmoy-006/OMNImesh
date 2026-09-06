import unittest
import time
from omnimesh.comms.serializer import MessageSerializer
from omnimesh.comms.protocol import MeshMessage, MessageType

class TestCommsSerializer(unittest.TestCase):
    def test_serializer_roundtrip(self):
        serializer = MessageSerializer()
        msg = MeshMessage(
            sender_id="node_1",
            msg_type=MessageType.STATE_BROADCAST,
            timestamp=time.time(),
            payload={"queue": [5, 2, 0, 8]},
        )
        packed = serializer.serialize(msg.to_dict())
        unpacked = serializer.deserialize(packed)
        self.assertEqual(unpacked["sender_id"], "node_1")
        self.assertEqual(unpacked["payload"]["queue"], [5, 2, 0, 8])

if __name__ == "__main__":
    unittest.main()
