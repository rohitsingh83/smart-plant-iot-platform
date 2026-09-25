# 🌿 Apex Smart Plant Care & Irrigation Platform (Virtual Digital Twin & SITL)

[![Live Dashboard](https://img.shields.io/badge/Live%20Dashboard-GitHub%20Pages%20%7C%20Vercel-success?style=for-the-badge&logo=vercel)](https://rohitsingh83.github.io/smart-plant-iot-platform/)
[![Deploy to Render](https://img.shields.io/badge/Deploy%20to-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://render.com/deploy?repo=https://github.com/rohitsingh83/smart-plant-iot-platform)
[![Database](https://img.shields.io/badge/Database-Supabase%20PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com/)

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.14-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-D71F00.svg?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![Docker](https://img.shields.io/badge/Docker-Multi--Stage-2496ED.svg?logo=docker&logoColor=white)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Live Production URLs:**
> - 🌐 **Live Web Dashboard:** [https://rohitsingh83.github.io/smart-plant-iot-platform/](https://rohitsingh83.github.io/smart-plant-iot-platform/)
> - 📦 **GitHub Repository:** [https://github.com/rohitsingh83/smart-plant-iot-platform](https://github.com/rohitsingh83/smart-plant-iot-platform)
> - ⚡ **Render 1-Click Blueprint:** [Deploy on Render](https://render.com/deploy?repo=https://github.com/rohitsingh83/smart-plant-iot-platform)
> - 🗄️ **Supabase Database:** Fully compatible with managed Supabase / Neon PostgreSQL URI connection strings.

A production-grade, placement-ready Cloud Computing, IoT, and Cyber-Physical Systems engineering platform. Features a zero-hardware-mandate **Software-in-the-Loop (SITL)** differential physics simulator, time-series telemetry store, cryptographic edge authentication, dual-threshold hysteresis control laws, a dead-man's switch daemon, and a real-time web dashboard.

---

## 🏛 Architectural Overview

```
 +-------------------------------------------------------------------------+
 |                               EDGE TIER                                 |
 |                                                                         |
 |  +--------------------------------+   +------------------------------+  |
 |  |  SITL Physics Simulator (Py)   |   |   Optional ESP32 Firmware    |  |
 |  |  - Differential drying model   |   |   - FreeRTOS non-blocking    |  |
 |  |  - Sinusoidal diurnal cycles   |   |   - Capacitive ADC Calib     |  |
 |  |  - Offline buffer & jitter     |   |   - Local emergency cutoff   |  |
 |  +---------------+----------------+   +--------------+---------------+  |
 |                  |                                   |                  |
 |                  +-----------------+-----------------+                  |
 |                                    |                                    |
 |             HMAC-SHA256 Signed JSON over HTTPS/REST                     |
 |             Headers: x-api-key, x-device-signature                      |
 +------------------------------------|------------------------------------+
                                      v
 +-------------------------------------------------------------------------+
 |                         CLOUD INGESTION GATEWAY                         |
 |                                                                         |
 |  +-------------------------------------------------------------------+  |
 |  | FastAPI Async Microservice & Reverse Proxy                         |  |
 |  |  - HMAC Signature Verification & Anti-Tamper Filter               |  |
 |  |  - Dead-Man's Switch Background Daemon (Heartbeat Watchdog)        |  |
 |  +------------------+--------------------------------+---------------+  |
 |                     |                                |                  |
 +---------------------|--------------------------------|------------------+
                       v                                v
 +----------------------------------+    +---------------------------------+
 |      INDUSTRIAL CONTROL LAW      |    |       PERSISTENCE LAYER         |
 |                                  |    |                                 |
 | - Dual-Threshold Hysteresis      |    | SQLite (Local) / PostgreSQL /   |
 | - Anti-Flapping Cooldown Lockout |    | TimescaleDB (Cloud Enterprise)  |
 | - Reservoir Guardrails (Cavitation|   |                                 |
 |   Prevention < 10% Cutoff)       |    | Tables: users, devices,         |
 | - Watchdog Timer Cap (Max 8.0s)  |    | readings, events, alerts        |
 +------------------+---------------+    +----------------+----------------+
                    |                                     |
                    +------------------+------------------+
                                       v
 +-------------------------------------------------------------------------+
 |                         OPERATOR DASHBOARD                              |
 |                                                                         |
 |  - Single-Page Application (HTML5 / Tailwind CSS / Vanilla JS)          |
 |  - Chart.js Dual-Axis Telemetry & Irrigation History                    |
 |  - Digital Twin State Display & Virtual Pump Glow Animation             |
 |  - Dynamic Botanical Presets (Succulents, Tropical, Tomatoes, Herbs)    |
 |  - Real-Time Operational Alarm Center with Acknowledgment               |
 +-------------------------------------------------------------------------+
```

---

## ⚡ Quickstart Guide (Local Execution)

### 1. Prerequisites
- Python 3.10+ (Tested up to Python 3.14)
- Git

### 2. Clone & Environment Setup
```bash
git clone https://github.com/yourusername/smart-plant-iot-platform.git
cd smart-plant-iot-platform

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
cp .env.example .env
```

### 3. Launch the Backend Gateway
```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```
- Interactive Swagger API Documentation: `http://localhost:8000/docs`
- Real-Time Web Dashboard: `http://localhost:8000/`

### 4. Launch the SITL Physics Simulator (In a Separate Terminal)
```bash
python sensor_simulator/simulator.py
```
Observe the physics simulator begin publishing signed telemetry, undergoing diurnal day/night cycles, and receiving automated irrigation pulses from the cloud control law!

---

## 🐳 Docker Container Orchestration

Run both the Cloud Ingest Gateway and the SITL Physics Simulator simultaneously with a single command:
```bash
docker compose up --build
```
Navigate to `http://localhost:8000/` in your browser to view the active Digital Twin dashboard.

---

## 🧪 Automated Test Suite

Execute the test suite validating industrial control laws, signature verification, cooldowns, and watchdog timeouts:
```bash
pytest -v tests/test_platform.py
```

---

## 📡 REST API & Ingest Recipes

### 1. Health & Liveness Probe
```bash
curl -X GET http://localhost:8000/api/v1/health
```

### 2. Ingest Cryptographically Signed Telemetry
```bash
# Ingest reading (Min threshold: 45%). Sending 30.0% triggers automated irrigation:
curl -X POST http://localhost:8000/api/v1/telemetry/ingest \
  -H "Content-Type: application/json" \
  -H "x-api-key: plant-care-edge-token-2026-secure" \
  -H "x-device-signature: 6a824e4d7e974e6fb296ad59f9c735d46816a7f343ecdb13f1e9c80521e16f39" \
  -d '{"device_id":"esp32-greenhouse-01","soil_moisture":30.0,"temperature":24.5,"humidity":58.0,"light_level":12000.0,"water_tank_level":90.0}'
```

### 3. Query Device Shadow & Health Index
```bash
curl -X GET http://localhost:8000/api/v1/devices/esp32-greenhouse-01/latest
```

### 4. Manual Actuation Pulse (Protected by Cooldown)
```bash
curl -X POST http://localhost:8000/api/v1/devices/esp32-greenhouse-01/actuate \
  -H "Content-Type: application/json" \
  -d '{"duration_seconds": 5.0, "reason": "Operator verification pulse"}'
```

### 5. Update Botanical Profile
```bash
curl -X PUT http://localhost:8000/api/v1/devices/esp32-greenhouse-01/config \
  -H "Content-Type: application/json" \
  -d '{"plant_species": "Succulents", "moisture_threshold_min": 18.0, "moisture_threshold_max": 35.0, "cooldown_minutes": 60.0}'
```

---

## 📄 License
This project is released under the **MIT License**.
