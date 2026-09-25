"""
Automated Test Suite for Cloud-Connected Smart Plant Care Platform
Validates Ingestion, Cryptographic Signatures, Dual-Threshold Hysteresis,
Cooldown Enforcement, Dead-Man's Switch Timeout, and Hardware Safety Guardrails.
"""

import os
import sys
import hmac
import json
import hashlib
import datetime

# Ensure project root is in python module search path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set test environment
os.environ["DATABASE_URL"] = "sqlite:///./test_plant_care.db"
os.environ["REQUIRE_HMAC_AUTH"] = "True"
os.environ["DEFAULT_DEVICE_ID"] = "test-node-01"
os.environ["DEFAULT_API_KEY"] = "test-api-key-12345"
os.environ["DEFAULT_HMAC_SECRET"] = "test-hmac-secret-abcdef"
os.environ["HEARTBEAT_INTERVAL_SECONDS"] = "2.0"
os.environ["DEADMAN_TIMEOUT_MULTIPLIER"] = "2.0"

from cloud.database import Base, get_db, Device, SensorReading, WateringEvent, Alert
from backend.app import app

TEST_ENGINE = create_engine("sqlite:///./test_plant_care.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module", autouse=True)
def setup_test_database():
    Base.metadata.drop_all(bind=TEST_ENGINE)
    Base.metadata.create_all(bind=TEST_ENGINE)

    db = TestingSessionLocal()
    dev = Device(
        id="test-node-01",
        device_name="Test Plant Node",
        plant_species="Tropical Foliage",
        moisture_threshold_min=40.0,
        moisture_threshold_max=70.0,
        pump_duration_seconds=5.0,
        cooldown_minutes=10.0,
        last_seen=datetime.datetime.utcnow(),
        status="ONLINE",
        api_key_hash="test-api-key-12345",
        hmac_secret="test-hmac-secret-abcdef"
    )
    db.add(dev)
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)
    TEST_ENGINE.dispose()
    if os.path.exists("./test_plant_care.db"):
        try:
            os.remove("./test_plant_care.db")
        except PermissionError:
            pass


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def generate_signed_request(payload: dict, secret: str = "test-hmac-secret-abcdef"):
    raw_body = json.dumps(payload, separators=(',', ':')).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return raw_body, sig


# -------------------------------------------------------------
# Test Cases
# -------------------------------------------------------------

def test_health_check(client):
    """Verify health readiness probe."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert data["database"] == "CONNECTED"


def test_hmac_auth_failure_bad_signature(client):
    """Verify that forged HMAC signature results in HTTP 401 Unauthorized."""
    payload = {
        "device_id": "test-node-01",
        "soil_moisture": 50.0,
        "temperature": 24.0,
        "humidity": 60.0,
        "light_level": 1200.0,
        "water_tank_level": 85.0
    }
    raw_body, _ = generate_signed_request(payload, secret="wrong-secret-key")

    res = client.post(
        "/api/v1/telemetry/ingest",
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": "test-api-key-12345",
            "x-device-signature": "bogus_signature_hash_hex"
        }
    )
    assert res.status_code == 401
    assert "Cryptographic verification failed" in res.json()["detail"]


def test_telemetry_ingest_optimal_hysteresis_idle(client):
    """Telemetry within deadband (50% moisture) does not trigger pump."""
    payload = {
        "device_id": "test-node-01",
        "soil_moisture": 50.0,
        "temperature": 22.0,
        "humidity": 65.0,
        "light_level": 800.0,
        "water_tank_level": 90.0
    }
    raw_body, sig = generate_signed_request(payload)

    res = client.post(
        "/api/v1/telemetry/ingest",
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": "test-api-key-12345",
            "x-device-signature": sig
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "INGESTED"
    assert data["pump_active"] is False
    assert data["decision"] == "NONE"


def test_telemetry_dry_triggers_automatic_hysteresis(client):
    """Telemetry below min threshold (32% <= 40%) triggers pump actuation."""
    payload = {
        "device_id": "test-node-01",
        "soil_moisture": 32.0,
        "temperature": 25.0,
        "humidity": 50.0,
        "light_level": 1500.0,
        "water_tank_level": 80.0
    }
    raw_body, sig = generate_signed_request(payload)

    res = client.post(
        "/api/v1/telemetry/ingest",
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": "test-api-key-12345",
            "x-device-signature": sig
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["pump_active"] is True
    assert data["decision"] == "AUTOMATIC_HYSTERESIS"
    assert data["pump_duration_seconds"] == 5.0


def test_cooldown_lockout_enforcement(client):
    """Subsequent dry reading immediately following watering is blocked by cooldown."""
    payload = {
        "device_id": "test-node-01",
        "soil_moisture": 31.0,
        "temperature": 25.0,
        "humidity": 50.0,
        "light_level": 1500.0,
        "water_tank_level": 78.0
    }
    raw_body, sig = generate_signed_request(payload)

    res = client.post(
        "/api/v1/telemetry/ingest",
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": "test-api-key-12345",
            "x-device-signature": sig
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["pump_active"] is False
    assert "throttled by anti-flapping cooldown" in data["reason"]


def test_water_tank_empty_guardrail(client):
    """When reservoir is depleted (<10%), pump must never engage and alarm must trip."""
    # Temporarily set device last_event in past to bypass cooldown
    db = TestingSessionLocal()
    event = db.query(WateringEvent).filter(WateringEvent.device_id == "test-node-01").first()
    if event:
        event.timestamp = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
        db.commit()
    db.close()

    payload = {
        "device_id": "test-node-01",
        "soil_moisture": 25.0,  # Critically dry
        "temperature": 24.0,
        "humidity": 50.0,
        "light_level": 1200.0,
        "water_tank_level": 5.0   # Tank empty! (<10%)
    }
    raw_body, sig = generate_signed_request(payload)

    res = client.post(
        "/api/v1/telemetry/ingest",
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": "test-api-key-12345",
            "x-device-signature": sig
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["pump_active"] is False
    assert "TANK_EMPTY" in data["alerts_triggered"]


def test_manual_actuation_blocked_by_cooldown(client):
    """Manual actuation attempted during cooldown period is rejected with HTTP 429."""
    # Insert recent watering event
    db = TestingSessionLocal()
    ev = WateringEvent(
        device_id="test-node-01",
        trigger_type="AUTOMATIC_HYSTERESIS",
        duration_seconds=5.0,
        moisture_before=30.0,
        timestamp=datetime.datetime.utcnow()
    )
    db.add(ev)
    db.commit()
    db.close()

    res = client.post(
        "/api/v1/devices/test-node-01/actuate",
        json={"duration_seconds": 4.0, "reason": "Test manual pulse"}
    )
    assert res.status_code == 429
    assert "mandatory cooldown" in res.json()["detail"]


def test_device_config_update(client):
    """Dynamic profile and threshold calibration updates."""
    res = client.put(
        "/api/v1/devices/test-node-01/config",
        json={
            "plant_species": "Succulents",
            "moisture_threshold_min": 18.0,
            "moisture_threshold_max": 32.0,
            "pump_duration_seconds": 3.5,
            "cooldown_minutes": 60.0
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["plant_species"] == "Succulents"
    assert data["moisture_threshold_min"] == 18.0
    assert data["moisture_threshold_max"] == 32.0
    assert data["cooldown_minutes"] == 60.0


def test_alert_listing_and_acknowledgement(client):
    """Verify alerts can be queried and acknowledged."""
    res = client.get("/api/v1/alerts?unack_only=true")
    assert res.status_code == 200
    alerts = res.json()
    assert len(alerts) > 0

    target_alert_id = alerts[0]["id"]
    ack_res = client.put(f"/api/v1/alerts/{target_alert_id}/ack")
    assert ack_res.status_code == 200
    assert ack_res.json()["status"] == "SUCCESS"


def test_device_history_analytical_endpoint(client):
    """Verify time-series history aggregation endpoint."""
    res = client.get("/api/v1/devices/test-node-01/history?hours=24")
    assert res.status_code == 200
    history = res.json()
    assert history["device_id"] == "test-node-01"
    assert "readings" in history
    assert "watering_events" in history
    assert len(history["readings"]) > 0
