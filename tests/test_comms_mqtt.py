import unittest
import time
from omnimesh.comms.mqtt_client import MeshMQTTClient
from omnimesh.comms.serializer import MessageSerializer
from omnimesh.tier1_edge.zspf_state_machine import ZSPFStateMachine, OperationalMode

class TestCommsMQTT(unittest.TestCase):
    def test_mqtt_client_subscriptions_and_callbacks(self):
        client = MeshMQTTClient(client_id="test_subscriber")
        client.connect()

        received_heartbeats = []
        received_states = []

        client.register_heartbeat_callback(lambda d: received_heartbeats.append(d))
        client.register_state_callback(lambda nid, d: received_states.append((nid, d)))

        # Publish heartbeat (binary msgpack payload)
        client.publish_heartbeat(source="orchestrator", timestamp=12345.67)
        self.assertEqual(len(received_heartbeats), 1)
        self.assertEqual(received_heartbeats[0]["source"], "orchestrator")
        self.assertEqual(received_heartbeats[0]["timestamp"], 12345.67)

        # Publish agent state (binary msgpack payload)
        client.publish_agent_state(
            node_id="node_0_1",
            phase=2,
            queues={"ew": 8.0, "ns": 3.0},
            timestamp=12345.80,
            threat_mode=1,
        )
        self.assertEqual(len(received_states), 1)
        nid, state_data = received_states[0]
        self.assertEqual(nid, "node_0_1")
        self.assertEqual(state_data["phase"], 2)
        self.assertEqual(state_data["queues"]["ew"], 8.0)
        self.assertEqual(state_data["threat_mode"], 1)

    def test_mqtt_sever_triggers_zspf_mode_2(self):
        zspf = ZSPFStateMachine()
        client = MeshMQTTClient(client_id="test_sever")
        client.register_disconnect_callback(lambda: zspf.notify_broker_disconnected())
        client.connect()

        self.assertEqual(zspf.current_mode, OperationalMode.MODE_0_FULL_MESH)
        
        # Sever connection
        client.sever_connection()
        self.assertFalse(client.is_connected)
        self.assertEqual(zspf.current_mode, OperationalMode.MODE_2_ISLAND)

if __name__ == "__main__":
    unittest.main()
