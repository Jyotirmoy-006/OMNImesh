"""
Unit tests for Human-in-the-Loop (HITL) Ethical Authorization Gateway
Verifies:
  1. Internal state lock blocking signal override on 2-node consensus
  2. PENDING_AUTHORIZATION state transition
  3. Dispatcher authorization release and directive execution
  4. Global bypass for headless statistical benchmarking
"""

import unittest
from omnimesh.tier2_orchestrator.human_in_loop import HumanInTheLoopGateway
from omnimesh.tier2_orchestrator.orchestrator import GlobalZoneOrchestrator

class TestHITLGateway(unittest.TestCase):
    def setUp(self):
        HumanInTheLoopGateway.GLOBAL_BYPASS = False
        self.gateway = HumanInTheLoopGateway(auto_approve_for_sim=False)

    def tearDown(self):
        HumanInTheLoopGateway.GLOBAL_BYPASS = False

    def test_consensus_triggers_pending_authorization_and_blocks_override(self):
        """
        Verifies Constraint 1:
        When 2-node consensus is verified, request_authorization blocks signal override
        output (returns False) and transitions to PENDING_AUTHORIZATION.
        """
        approved = self.gateway.request_authorization(
            plate="SUSPECT-892",
            location="node_2_1",
            confidence=0.96,
            confirmed_nodes=["node_2_0", "node_2_1"],
        )
        self.assertFalse(approved)
        self.assertEqual(self.gateway.state, "PENDING_AUTHORIZATION")
        self.assertTrue(self.gateway.is_locked)
        self.assertIsNotNone(self.gateway.pending_alert)
        self.assertEqual(self.gateway.pending_alert["plate"], "SUSPECT-892")

    def test_explicit_dispatcher_authorization_releases_lock(self):
        """
        Verifies Constraint 1 & 2:
        Calling authorize() unlocks the gateway, transitions state to AUTHORIZED,
        and records the dispatcher identifier.
        """
        self.gateway.request_authorization("SUSPECT-892", "node_2_1", 0.96)
        self.assertEqual(self.gateway.state, "PENDING_AUTHORIZATION")

        res = self.gateway.authorize(approver_id="dispatcher_lead")
        self.assertEqual(res["status"], "success")
        self.assertEqual(self.gateway.state, "AUTHORIZED")
        self.assertFalse(self.gateway.is_locked)
        self.assertEqual(len(self.gateway.authorization_history), 1)
        self.assertEqual(self.gateway.authorization_history[0]["approver_id"], "dispatcher_lead")

    def test_dispatcher_rejection(self):
        """Verifies rejection transitions to REJECTED and maintains lock."""
        self.gateway.request_authorization("SUSPECT-892", "node_2_1", 0.96)
        res = self.gateway.reject(approver_id="dispatcher_lead", reason="False positive plate match")
        self.assertEqual(res["status"], "rejected")
        self.assertEqual(self.gateway.state, "REJECTED")
        self.assertTrue(self.gateway.is_locked)
        self.assertIsNone(self.gateway.pending_alert)

    def test_headless_evaluation_global_bypass(self):
        """
        Verifies Constraint 4:
        GLOBAL_BYPASS automatically bypasses HITL lock during headless statistical evaluations.
        """
        HumanInTheLoopGateway.GLOBAL_BYPASS = True
        approved = self.gateway.request_authorization("SUSPECT-892", "node_2_1", 0.96)
        self.assertTrue(approved)
        self.assertEqual(self.gateway.state, "AUTHORIZED")
        self.assertFalse(self.gateway.is_locked)

    def test_orchestrator_blocks_and_executes_on_authorization(self):
        """
        Verifies integration between GlobalZoneOrchestrator and HumanInTheLoopGateway.
        """
        orchestrator = GlobalZoneOrchestrator(zone_id="zone_alpha", auto_approve_sim=False)

        # 1. Multi-node consensus alert received: must be blocked by HITL lock
        directives = orchestrator.process_consensus_alert(
            plate="SUSPECT-892",
            confirmed_nodes=["node_2_0", "node_2_1"],
            confidence=0.96,
        )
        self.assertEqual(directives, {})
        self.assertEqual(orchestrator.hitl_gateway.state, "PENDING_AUTHORIZATION")

        # 2. Dispatcher explicitly authorizes containment
        exec_directives = orchestrator.authorize_containment(approver_id="dispatcher_01")
        self.assertEqual(orchestrator.hitl_gateway.state, "AUTHORIZED")
        self.assertIn("node_2_1", exec_directives)

if __name__ == "__main__":
    unittest.main()
