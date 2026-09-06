"""
Omni-Mesh Decentralized MQTT Client
Implements asynchronous MQTT publish/subscribe using paho-mqtt and MessagePack,
with active subscriptions to Tier-2 heartbeats and Tier-1 neighbor states.
"""

from typing import Callable, Optional, Dict, Any, List
import time
import threading
import paho.mqtt.client as mqtt

from omnimesh.utils.logger import logger
from .serializer import MessageSerializer

class MeshMQTTClient:
    """
    Decoupled asynchronous MQTT client supporting binary MessagePack payloads.
    Subscribes to:
      - omnimesh/tier2/heartbeat (Tier-2 orchestrator liveness)
      - omnimesh/tier1/+/state (Tier-1 neighbor state sharing)
    """

    TOPIC_HEARTBEAT = "omnimesh/tier2/heartbeat"
    TOPIC_TIER1_STATE = "omnimesh/tier1/+/state"

    def __init__(
        self,
        client_id: str = "omni_mesh_node",
        host: str = "localhost",
        port: int = 1883,
        keepalive: int = 60,
    ):
        self.client_id = client_id
        self.host = host
        self.port = port
        self.keepalive = keepalive
        self.serializer = MessageSerializer()

        self.is_connected = False
        self.use_simulation_fallback = False

        # Callbacks
        self.on_heartbeat_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self.on_state_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        self.on_disconnect_callbacks: List[Callable[[], None]] = []
        self.on_connect_callbacks: List[Callable[[], None]] = []

        # Paho Client setup
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.client_id)
        except Exception:
            self.client = mqtt.Client(client_id=self.client_id)

        self.client.on_connect = self._on_paho_connect
        self.client.on_message = self._on_paho_message
        self.client.on_disconnect = self._on_paho_disconnect

        self._lock = threading.Lock()

    def register_heartbeat_callback(self, cb: Callable[[Dict[str, Any]], None]):
        """Registers listener for Tier-2 heartbeat events."""
        self.on_heartbeat_callbacks.append(cb)

    def register_state_callback(self, cb: Callable[[str, Dict[str, Any]], None]):
        """Registers listener for Tier-1 neighbor state updates."""
        self.on_state_callbacks.append(cb)

    def register_disconnect_callback(self, cb: Callable[[], None]):
        """Registers listener for MQTT disconnect events."""
        self.on_disconnect_callbacks.append(cb)

    def register_connect_callback(self, cb: Callable[[], None]):
        """Registers listener for MQTT connection events."""
        self.on_connect_callbacks.append(cb)

    def _on_paho_connect(self, client, userdata, flags, rc, properties=None):
        """Paho on_connect callback: establishes required subscriptions."""
        if rc == 0 or rc == mqtt.MQTT_ERR_SUCCESS:
            self.is_connected = True
            logger.info(f"MQTT Client [{self.client_id}] connected to broker at {self.host}:{self.port}")

            # Subscribe to Tier-2 heartbeat and Tier-1 neighbor state
            self.client.subscribe([(self.TOPIC_HEARTBEAT, 0), (self.TOPIC_TIER1_STATE, 0)])
            logger.info(f"Subscribed to [{self.TOPIC_HEARTBEAT}] and [{self.TOPIC_TIER1_STATE}]")

            for cb in self.on_connect_callbacks:
                try:
                    cb()
                except Exception as e:
                    logger.error(f"Error in on_connect callback: {e}")
        else:
            self.is_connected = False
            logger.warning(f"MQTT connection failed with code {rc}")

    def _on_paho_disconnect(self, client, userdata, rc=None, properties=None):
        """Paho on_disconnect callback."""
        self.is_connected = False
        logger.warning(f"MQTT Client [{self.client_id}] disconnected from broker.")
        for cb in self.on_disconnect_callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"Error in on_disconnect callback: {e}")

    def _on_paho_message(self, client, userdata, msg):
        """Handles incoming MQTT messages with binary MessagePack payload decoding."""
        self._dispatch_message(msg.topic, msg.payload)

    def _dispatch_message(self, topic: str, payload: bytes):
        """Deserializes binary MessagePack payload and triggers appropriate handlers."""
        try:
            data = self.serializer.deserialize(payload)
        except Exception as e:
            logger.error(f"Failed to deserialize binary payload on topic {topic}: {e}")
            return

        # Tier-2 Heartbeat topic
        if mqtt.topic_matches_sub(self.TOPIC_HEARTBEAT, topic):
            for cb in self.on_heartbeat_callbacks:
                try:
                    cb(data)
                except Exception as e:
                    logger.error(f"Error in heartbeat handler: {e}")

        # Tier-1 Neighbor State topic
        elif mqtt.topic_matches_sub(self.TOPIC_TIER1_STATE, topic):
            # Extract node_id from topic "omnimesh/tier1/<node_id>/state"
            parts = topic.split("/")
            node_id = parts[2] if len(parts) >= 3 else data.get("node_id", "unknown")
            for cb in self.on_state_callbacks:
                try:
                    cb(node_id, data)
                except Exception as e:
                    logger.error(f"Error in state handler: {e}")

    def connect(self) -> bool:
        """
        Attempts connection to the MQTT broker.
        If no broker daemon is running, seamlessly operates in software simulation mode.
        """
        try:
            self.client.connect(self.host, self.port, keepalive=self.keepalive)
            self.client.loop_start()
            self.is_connected = True
            # Explicitly subscribe on connect
            self.client.subscribe([(self.TOPIC_HEARTBEAT, 0), (self.TOPIC_TIER1_STATE, 0)])
            logger.info(f"MQTT Client connected to {self.host}:{self.port} with active subscriptions.")
            return True
        except Exception as e:
            logger.warning(
                f"No external MQTT broker detected at {self.host}:{self.port} ({e}). "
                f"Operating in pure-software simulation MQTT bus mode."
            )
            self.use_simulation_fallback = True
            self.is_connected = True
            for cb in self.on_connect_callbacks:
                try:
                    cb()
                except Exception:
                    pass
            return True

    def disconnect(self):
        """Disconnects the client and triggers disconnect callbacks."""
        with self._lock:
            self.is_connected = False
            try:
                self.client.disconnect()
                self.client.loop_stop()
            except Exception:
                pass
            logger.warning(f"MQTT Client [{self.client_id}] connection terminated.")
            for cb in self.on_disconnect_callbacks:
                try:
                    cb()
                except Exception as e:
                    logger.error(f"Error in disconnect callback: {e}")

    def sever_connection(self):
        """Simulates complete broker disconnect / network partition."""
        self.disconnect()

    def publish_agent_state(
        self,
        node_id: str,
        phase: int,
        queues: Dict[str, float],
        timestamp: Optional[float] = None,
        threat_mode: int = 0,
    ) -> bool:
        """
        Serializes agent state vector into binary msgpack and publishes to omnimesh/tier1/{node_id}/state.
        """
        if not self.is_connected:
            return False

        ts = timestamp if timestamp is not None else time.time()
        payload = self.serializer.encode_agent_state(
            node_id=node_id,
            phase=phase,
            queues=queues,
            timestamp=ts,
            threat_mode=threat_mode,
        )
        topic = f"omnimesh/tier1/{node_id}/state"

        if self.use_simulation_fallback:
            self._dispatch_message(topic, payload)
            return True

        try:
            self.client.publish(topic, payload, qos=0)
            return True
        except Exception as e:
            logger.error(f"Failed to publish agent state to {topic}: {e}")
            return False

    def publish_heartbeat(
        self,
        source: str = "tier2_orchestrator",
        timestamp: Optional[float] = None,
    ) -> bool:
        """
        Publishes a binary msgpack heartbeat to omnimesh/tier2/heartbeat.
        """
        if not self.is_connected:
            return False

        ts = timestamp if timestamp is not None else time.time()
        data = {
            "source": str(source),
            "timestamp": float(ts),
            "status": "HEALTHY",
        }
        payload = self.serializer.serialize(data)
        topic = self.TOPIC_HEARTBEAT

        if self.use_simulation_fallback:
            self._dispatch_message(topic, payload)
            return True

        try:
            self.client.publish(topic, payload, qos=0)
            return True
        except Exception as e:
            logger.error(f"Failed to publish heartbeat to {topic}: {e}")
            return False
