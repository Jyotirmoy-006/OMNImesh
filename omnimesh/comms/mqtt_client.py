from typing import Callable, Optional
from omnimesh.utils.logger import logger
from .serializer import MessageSerializer
from .protocol import MeshMessage

class MeshMQTTClient:
    """
    Decoupled asynchronous MQTT client supporting binary MessagePack payloads.
    """
    def __init__(self, client_id: str, host: str = "localhost", port: int = 1883):
        self.client_id = client_id
        self.host = host
        self.port = port
        self.serializer = MessageSerializer()
        self.is_connected = False
        self.on_message_callback: Optional[Callable[[MeshMessage], None]] = None

    def connect(self):
        # Mock client connection for tests/simulation
        self.is_connected = True
        logger.info(f"MQTT Client [{self.client_id}] connected to {self.host}:{self.port}")

    def publish_message(self, topic: str, message: MeshMessage):
        payload = self.serializer.serialize(message.to_dict())
        # logger.debug(f"Published {len(payload)} bytes to {topic}")

    def subscribe(self, topic: str, callback: Callable[[MeshMessage], None]):
        self.on_message_callback = callback
        logger.info(f"MQTT Client [{self.client_id}] subscribed to {topic}")
