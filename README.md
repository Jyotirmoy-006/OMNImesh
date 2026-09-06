# Omni-Mesh: Decentralized Two-Tiered Traffic Optimization & Edge Security

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Repository](https://img.shields.io/badge/GitHub-OMNImesh-blue?logo=github)](https://github.com/Jyotirmoy-006/OMNImesh)

Omni-Mesh is a novel, two-tiered Multi-Agent System (MAS) that bridges adaptive civilian traffic signal control with real-time public safety operations on commodity edge hardware (Raspberry Pi 4B).

---

## 🏛️ System Architecture

```
+-----------------------------------------------------------------------------------+
|                        TIER 2: GLOBAL ZONE ORCHESTRATOR                           |
|   - Macro-Anomaly Detection, City-Wide Watchlist Management & Containment Gate    |
+------------------------------------------+----------------------------------------+
                                           | Heartbeat (1 Hz) / Directives
                                           v
+-----------------------------------------------------------------------------------+
|               TIER 1: THE DECENTRALIZED EDGE MESH (Intersection Nodes)             |
|                                                                                   |
|  [Hardware: Raspberry Pi 4B + NCNN INT8 + Decoupled Multi-Threading]              |
|                                                                                   |
|   [Thread A: Perception (15 FPS)] -> YOLOv8n NCNN INT8 Real-time Queue Tracking   |
|   [Thread B: Event ANPR (1-3 FPS)] -> Fast OCR with Multi-Node Temporal Consensus |
|   [Thread C: RL Control (1-2 Hz)]  -> Discrete Phase Switching Policy             |
|   [Thread D: Comms (Async I/O)]    -> P2P Green Wave & 3-Mode ZSPF State Machine  |
+-----------------------------------------------------------------------------------+
```

---

## 🚀 Key Innovations
1. **Transponder-Free P2P Green Wave**: Visual detection of emergency vehicles propagates rolling downstream green preemption without vehicle-side GPS/transponders.
2. **Autonomous ANPR Threat Containment**: First system directly connecting camera plate recognition with signal barrier traps without requiring 2–15 minute human dispatch latency.
3. **Active Zero Single Point of Failure (ZSPF)**:
   - **Mode 0 (Full Mesh)**: Central Orchestrator active + P2P RL.
   - **Mode 1 (Autonomous P2P)**: Orchestrator offline; pure MARL state exchange.
   - **Mode 2 (Island Mode)**: Broker offline; atomic fallback to local Max-Pressure with bounded suboptimality ($\le 25\%$).

---

## 📂 Project Structure
```
omnimesh/
├── configs/                   # YAML configurations (edge, orchestrator, simulation, MQTT)
├── data/                      # Network topologies, test watchlists, and synthetic frames
├── omnimesh/
│   ├── tier1_edge/            # EdgeNodeAgent, policy inference, and ZSPF state machine
│   ├── tier2_orchestrator/    # Zone Orchestrator, rule engine, and watchlist tracking
│   ├── comms/                 # Async MQTT, MessagePack serialization, and P2P protocols
│   ├── vision/                # YOLOv8 detector, ANPR OCR, and multi-node consensus
│   ├── simulation/            # SUMO/TraCI & CityFlow wrappers and benchmark harnesses
│   └── utils/                 # Logging, metrics, and thermal trackers
├── scripts/                   # CLI entry points and setup scripts
└── tests/                     # Unit and integration test suite
```

---

## 🛠️ Quickstart

### 1. Install Dependencies
```bash
pip install -e .
pip install -r requirements.txt
```

### 2. Run Tests
```bash
pytest tests/
```

### 3. Launch Simulation Harness
```bash
python scripts/run_simulation.py --config configs/simulation_config.yaml
```

---

## 📄 References & Roadmap
Detailed research analysis, literature review, and 20-week milestone schedules are documented in [ROADMAP.md](ROADMAP.md).
