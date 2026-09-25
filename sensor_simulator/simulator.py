"""
Software-in-the-Loop (SITL) Physics & Edge Simulator
Simulates a multi-variable physical agronomic environment:
- Exponential soil moisture desiccation driven by temperature & solar flux.
- 24-hour diurnal sinusoidal cycles for solar radiation, ambient temperature, and humidity.
- Hydrological absorption dynamics following irrigation pump actuation.
- Realistic network conditions: packet dropouts, jitter, offline circular buffering, and HMAC-SHA256 signing.
"""

import os
import sys
import time
import math
import json
import hmac
import random
import hashlib
import requests
import datetime
from collections import deque
from typing import Dict, Any, Optional

# Configuration via environment or defaults
BACKEND_URL = os.getenv("SIMULATOR_BACKEND_URL", "http://localhost:8000")
DEVICE_ID = os.getenv("DEVICE_ID", "esp32-greenhouse-01")
API_KEY = os.getenv("DEVICE_API_KEY", "plant-care-edge-token-2026-secure")
HMAC_SECRET = os.getenv("HMAC_SECRET", "hmac-secret-key-plant-guard-99228811")
REPORT_INTERVAL = float(os.getenv("REPORT_INTERVAL_SECONDS", "3.0"))  # Real-world send cadence
TIME_ACCELERATION = float(os.getenv("TIME_ACCELERATION", "120.0"))     # 1 real sec = 120 sim sec
NETWORK_DROPOUT_RATE = float(os.getenv("NETWORK_DROPOUT_RATE", "0.05")) # 5% simulated packet loss
MAX_JITTER_SECONDS = float(os.getenv("SIMULATOR_JITTER_MAX_SECONDS", "0.3"))


class PlantPhysicsTwin:
    """
    Continuous differential state machine modeling agronomic physics.
    """
    def __init__(self):
        # State variables
        self.soil_moisture: float = 62.0      # Volumetric %
        self.water_tank_level: float = 95.0    # Reservoir %
        self.temperature: float = 23.5         # °C
        self.humidity: float = 60.0            # %
        self.light_level: float = 5000.0       # Lux

        # Transient actuation states
        self.pump_active: bool = False
        self.pump_remaining_seconds: float = 0.0

        # Physical constants
        self.k_evaporation: float = 0.00045    # Moisture decay coefficient
        self.absorption_rate: float = 4.2      # Moisture rise per second during pumping
        self.tank_depletion_rate: float = 0.8  # Tank % used per second of pumping

        # Simulation clock
        self.simulated_seconds: float = 8.0 * 3600.0  # Start at 08:00 AM

    def step(self, delta_sim_seconds: float):
        """Advances physics equations by delta_sim_seconds."""
        self.simulated_seconds = (self.simulated_seconds + delta_sim_seconds) % 86400.0

        # 1. Diurnal cycle (24-hour sun cycle)
        # Solar noon at 12:00 (43200 seconds)
        solar_phase = (self.simulated_seconds / 86400.0) * 2.0 * math.pi
        sun_elevation = math.sin(solar_phase - (math.pi / 2.0))  # -1 at midnight, +1 at noon

        # Solar radiation & light
        if sun_elevation > 0:
            self.light_level = max(50.0, sun_elevation * 65000.0 + random.uniform(-200.0, 200.0))
        else:
            self.light_level = max(5.0, 15.0 + random.uniform(-5.0, 5.0))  # Ambient night darkness

        # Temperature: Base 20°C, amplitude 9°C, lagging solar peak by ~2 hours (0.5 rad)
        temp_wave = math.sin(solar_phase - (math.pi / 2.0) - 0.5)
        self.temperature = round(21.0 + (8.5 * temp_wave) + random.uniform(-0.15, 0.15), 2)

        # Humidity: Inversely correlated with temperature
        norm_temp = (self.temperature - 12.0) / 20.0
        self.humidity = max(20.0, min(95.0, round(85.0 - (norm_temp * 45.0) + random.uniform(-0.5, 0.5), 1)))

        # 2. Irrigation Reaction vs. Evapotranspiration
        if self.pump_active and self.pump_remaining_seconds > 0:
            active_duration = min(delta_sim_seconds, self.pump_remaining_seconds)
            # Moisture rises quickly to saturation
            saturation_cap = 88.0
            if self.soil_moisture < saturation_cap:
                self.soil_moisture += self.absorption_rate * (active_duration / 10.0)
            self.soil_moisture = min(saturation_cap, self.soil_moisture)

            # Deplete reservoir
            self.water_tank_level = max(0.0, self.water_tank_level - (self.tank_depletion_rate * (active_duration / 10.0)))
            self.pump_remaining_seconds -= active_duration
            if self.pump_remaining_seconds <= 0:
                self.pump_active = False
        else:
            self.pump_active = False
            # Natural drying exponential decay:
            # dM/dt = -k * (T / 25) * (1 + light / 10000) * dt
            thermal_factor = max(0.5, self.temperature / 24.0)
            light_factor = 1.0 + (self.light_level / 12000.0)
            evaporation_delta = self.k_evaporation * thermal_factor * light_factor * delta_sim_seconds
            self.soil_moisture = max(5.0, self.soil_moisture - evaporation_delta)

        self.soil_moisture = round(self.soil_moisture, 2)
        self.water_tank_level = round(self.water_tank_level, 2)

    def trigger_watering(self, duration_seconds: float):
        """Instruct the physical plant twin to intake water."""
        self.pump_active = True
        self.pump_remaining_seconds = duration_seconds


class SITLSimulatorClient:
    """
    Resilient edge network client featuring SHA-256 HMAC signing,
    jitter injection, packet drop simulation, and offline buffer queue.
    """
    def __init__(self):
        self.physics = PlantPhysicsTwin()
        self.offline_queue: deque = deque(maxlen=200)
        self.consecutive_failures = 0

    def sign_payload(self, raw_bytes: bytes) -> str:
        """Computes HMAC-SHA256 signature using edge device pre-shared secret."""
        return hmac.new(
            HMAC_SECRET.encode("utf-8"),
            raw_bytes,
            hashlib.sha256
        ).hexdigest()

    def transmit_payload(self, telemetry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Sends telemetry packet with cryptographic authentication headers.
        Simulates network latency and dropouts.
        """
        raw_body = json.dumps(telemetry, separators=(',', ':')).encode("utf-8")
        signature = self.sign_payload(raw_body)

        headers = {
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "x-device-signature": signature
        }

        # Simulated Jitter
        if MAX_JITTER_SECONDS > 0:
            time.sleep(random.uniform(0.01, MAX_JITTER_SECONDS))

        # Simulated Network Dropout
        if random.random() < NETWORK_DROPOUT_RATE:
            print(f" [Network Simulation] Packet dropped by simulated airlink jitter!")
            return None

        url = f"{BACKEND_URL}/api/v1/telemetry/ingest"
        try:
            response = requests.post(url, data=raw_body, headers=headers, timeout=4.0)
            if response.status_code == 200:
                self.consecutive_failures = 0
                return response.json()
            else:
                print(f" [Edge Ingest Warning] HTTP {response.status_code}: {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            self.consecutive_failures += 1
            # Exponential backoff with jitter indicator
            backoff = min(8.0, (2 ** min(self.consecutive_failures, 4))) + random.uniform(0.1, 0.5)
            print(f" [Connection Error] Backend offline ({e}). Backing off {backoff:.2f}s...")
            return None

    def flush_offline_buffer(self):
        """Flushes buffered packets when network connectivity is re-established."""
        if not self.offline_queue:
            return
        print(f" [Buffer Management] Flushing {len(self.offline_queue)} queued telemetry records...")
        flushed_count = 0
        while self.offline_queue:
            buffered_packet = self.offline_queue[0]
            resp = self.transmit_payload(buffered_packet)
            if resp:
                self.offline_queue.popleft()
                flushed_count += 1
            else:
                break
        print(f" [Buffer Management] Flushed {flushed_count} packets successfully.")

    def run(self):
        """Main simulation execution loop."""
        print("=" * 70)
        print(" APEX SMART PLANT CARE: SITL PHYSICS SIMULATOR (VIRTUAL TWIN)")
        print("=" * 70)
        print(f" Device Target: {DEVICE_ID}")
        print(f" Ingest URL:    {BACKEND_URL}/api/v1/telemetry/ingest")
        print(f" Real Cadence:  {REPORT_INTERVAL}s | Time Acceleration: {TIME_ACCELERATION}x")
        print(f" Security:      HMAC-SHA256 Payload Signing Enabled")
        print("=" * 70)

        last_real_time = time.time()

        try:
            while True:
                current_real_time = time.time()
                elapsed_real = current_real_time - last_real_time
                last_real_time = current_real_time

                # Step physical simulation
                delta_sim_seconds = elapsed_real * TIME_ACCELERATION
                self.physics.step(delta_sim_seconds)

                # Format edge telemetry reading
                payload = {
                    "device_id": DEVICE_ID,
                    "soil_moisture": self.physics.soil_moisture,
                    "temperature": self.physics.temperature,
                    "humidity": self.physics.humidity,
                    "light_level": self.physics.light_level,
                    "water_tank_level": self.physics.water_tank_level,
                    "timestamp": datetime.datetime.utcnow().isoformat()
                }

                # Attempt transmission
                response = self.transmit_payload(payload)

                sim_hours = int(self.physics.simulated_seconds // 3600)
                sim_mins = int((self.physics.simulated_seconds % 3600) // 60)
                sim_clock_str = f"{sim_hours:02d}:{sim_mins:02d}"

                if response:
                    pump_status = "PUMPING" if self.physics.pump_active else "IDLE"
                    print(
                        f"[{sim_clock_str}] Ingest OK | "
                        f"Moist: {self.physics.soil_moisture:5.1f}% | "
                        f"Temp: {self.physics.temperature:4.1f}°C | "
                        f"Light: {self.physics.light_level:5.0f}lx | "
                        f"Tank: {self.physics.water_tank_level:5.1f}% | "
                        f"Pump: {pump_status}"
                    )

                    # Check if cloud decision commanded irrigation
                    if response.get("pump_active") and response.get("pump_duration_seconds", 0) > 0:
                        duration = response["pump_duration_seconds"]
                        print(f" >>> [ACTUATION COMMAND RECEIVED] Irrigating for {duration:.1f}s: {response.get('reason')}")
                        self.physics.trigger_watering(duration)

                    # Try clearing offline buffer if any
                    if self.offline_queue:
                        self.flush_offline_buffer()
                else:
                    # Queue reading to offline buffer
                    self.offline_queue.append(payload)
                    print(
                        f"[{sim_clock_str}] Offline buffer stored ({len(self.offline_queue)} queued) | "
                        f"Moist: {self.physics.soil_moisture:5.1f}%"
                    )

                time.sleep(REPORT_INTERVAL)

        except KeyboardInterrupt:
            print("\n[Simulator Shutdown] SITL physics daemon halted gracefully.")


if __name__ == "__main__":
    simulator = SITLSimulatorClient()
    simulator.run()
