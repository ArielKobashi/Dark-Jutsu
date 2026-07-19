import unittest
import sys
import json
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import servidor_eleicao_darkjutsu as election
from servidor_eleicao_darkjutsu import decide_leader


CONFIG = {"preferredReturnGraceSeconds": 90}


def node(name, priority, *, eligible=True, ready_since=0):
    return {"computer": name, "priority": priority, "eligible": eligible, "readySinceEpoch": ready_since}


class ElectionTests(unittest.TestCase):
    def test_preferred_wins_without_lease(self):
        self.assertEqual(decide_leader(CONFIG, {"A": node("A", 10), "B": node("B", 20)}, {}, now=1000), "A")

    def test_next_candidate_wins_when_preferred_is_down(self):
        nodes = {"A": node("A", 10, eligible=False), "B": node("B", 20)}
        self.assertEqual(decide_leader(CONFIG, nodes, {}, now=1000), "B")

    def test_current_leader_is_kept_during_preferred_grace(self):
        nodes = {"A": node("A", 10, ready_since=950), "B": node("B", 20, ready_since=100)}
        self.assertEqual(decide_leader(CONFIG, nodes, {"leader": "B", "expiresAtEpoch": 1100}, now=1000), "B")

    def test_preferred_reclaims_after_stability_window(self):
        nodes = {"A": node("A", 10, ready_since=800), "B": node("B", 20, ready_since=100)}
        self.assertEqual(decide_leader(CONFIG, nodes, {"leader": "B", "expiresAtEpoch": 1100}, now=1000), "A")

    def test_expired_lease_is_replaced(self):
        nodes = {"A": node("A", 10), "B": node("B", 20)}
        self.assertEqual(decide_leader(CONFIG, nodes, {"leader": "B", "expiresAtEpoch": 999}, now=1000), "A")

    def test_no_eligible_candidate_returns_none(self):
        self.assertIsNone(decide_leader(CONFIG, {"A": node("A", 10, eligible=False)}, {}, now=1000))

    def test_standby_without_api_can_be_selected(self):
        nodes = {"A": node("A", 10) | {"apiHealthy": False}, "B": node("B", 20)}
        self.assertEqual(decide_leader(CONFIG, nodes, {}, now=1000), "A")

    def test_leader_without_api_after_grace_is_replaced(self):
        config = CONFIG | {"leaderApiStartupGraceSeconds": 45}
        nodes = {
            "A": node("A", 10) | {"apiHealthy": False},
            "B": node("B", 20) | {"apiHealthy": True},
        }
        lease = {"leader": "A", "expiresAtEpoch": 1100, "acquiredAtEpoch": 900}
        self.assertEqual(decide_leader(config, nodes, lease, now=1000), "B")

    @unittest.skip("Teste de integracao SMB executado somente no ambiente de homologacao.")
    def test_heartbeat_lease_and_failover_in_temporary_share(self):
        original = {name: getattr(election, name) for name in (
            "SHARE_ROOT", "CONFIG_PATH", "STATUS_DIR", "NODES_DIR", "LEASE_PATH", "LOCK_DIR"
        )}
        old_computer = os.environ.get("COMPUTERNAME")
        try:
            with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
                root = Path(tmp)
                election.SHARE_ROOT = root
                election.CONFIG_PATH = root / "scripts" / "servidores_config.json"
                election.STATUS_DIR = root / "status"
                election.NODES_DIR = election.STATUS_DIR / "nodes"
                election.LEASE_PATH = election.STATUS_DIR / "leader_lease.json"
                election.LOCK_DIR = election.STATUS_DIR / "leader-election.lock"
                election.CONFIG_PATH.parent.mkdir(parents=True)
                election.CONFIG_PATH.write_text(json.dumps({
                    "leaseSeconds": 35,
                    "heartbeatTimeoutSeconds": 60,
                    "preferredReturnGraceSeconds": 0,
                    "candidates": [
                        {"computer": "A", "priority": 10},
                        {"computer": "B", "priority": 20},
                    ],
                }), encoding="utf-8")
                os.environ["COMPUTERNAME"] = "A"
                election.publish_heartbeat(ready=True, api_healthy=False, ips=["10.0.0.1"])
                os.environ["COMPUTERNAME"] = "B"
                election.publish_heartbeat(ready=True, api_healthy=False, ips=["10.0.0.2"])
                os.environ["COMPUTERNAME"] = "A"
                self.assertTrue(election.election_tick()["isLeader"])
                os.environ["COMPUTERNAME"] = "B"
                self.assertEqual(election.election_tick()["leader"], "A")
                a_path = election.NODES_DIR / "A.json"
                a = json.loads(a_path.read_text(encoding="utf-8"))
                a["updatedAtEpoch"] = 1
                a_path.write_text(json.dumps(a), encoding="utf-8")
                decision = election.election_tick()
                self.assertTrue(decision["isLeader"])
                self.assertEqual(decision["leader"], "B")
        finally:
            for name, value in original.items():
                setattr(election, name, value)
            if old_computer is None:
                os.environ.pop("COMPUTERNAME", None)
            else:
                os.environ["COMPUTERNAME"] = old_computer


if __name__ == "__main__":
    unittest.main()
