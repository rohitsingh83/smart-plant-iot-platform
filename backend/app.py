"""
Cloud Ingest API & IoT Gateway Core
FastAPI Microservice managing Telemetry Ingestion, Device State Shadow,
Dead-Man's Switch Heartbeat Daemon, Security Middleware, and REST APIs.
"""

import os
import time
import hmac
import hashlib
import asyncio
import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Header, Request, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import desc

from cloud.database import (
    get_db,
    init_db,
    SessionLocal,
    Device,
    SensorReading,
    WateringEvent,
    Alert
)
from backend.schemas import (
    TelemetryIngestRequest,
    TelemetryIngestResponse,
    DeviceResponse,
    DeviceUpdate,
    SensorReadingResponse,
    WateringEventResponse,
    ManualActuateRequest,
    ManualActuateResponse,
    AlertResponse,
    DeviceHistoryResponse,
    HealthResponse
)
from automation.watering_engine import (
    evaluate_telemetry,
    validate_manual_actuation
)
from automation.plant_profiles import list_profiles, get_profile

START_TIME = time.time()
REQUIRE_HMAC_AUTH = os.getenv("REQUIRE_HMAC_AUTH", "True").lower() in ("true", "1", "yes")
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "10.0"))
DEADMAN_MULTIPLIER = float(os.getenv("DEADMAN_TIMEOUT_MULTIPLIER", "2.5"))
TIMEOUT_THRESHOLD_SECONDS = HEARTBEAT_INTERVAL * DEADMAN_MULTIPLIER

# -------------------------------------------------------------
# Background Daemon: Dead-Man's Switch & Heartbeat Watchdog
# -------------------------------------------------------------
async def deadman_switch_monitor_loop():
    """
    Continuous background loop evaluating:
    CurrentTime - LastSeenTimestamp > ExpectedInterval * 2.5
    Transitions device status to OFFLINE automatically and emits a CRITICAL alert.
    """
    while True:
        try:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            db: Session = SessionLocal()
            try:
                now = datetime.datetime.utcnow()
                active_devices = db.query(Device).filter(Device.status != "OFFLINE").all()

                for device in active_devices:
                    elapsed = (now - device.last_seen).total_seconds()
                    if elapsed > TIMEOUT_THRESHOLD_SECONDS:
                        device.status = "OFFLINE"

                        # Check if a recent unacknowledged timeout alert already exists
                        existing_alert = (
                            db.query(Alert)
                            .filter(
                                Alert.device_id == device.id,
                                Alert.alert_type == "DEVICE_TIMEOUT",
                                Alert.acknowledged == False
                            )
                            .first()
                        )
                        if not existing_alert:
                            timeout_alert = Alert(
                                device_id=device.id,
                                severity="CRITICAL",
                                alert_type="DEVICE_TIMEOUT",
                                message=(
                                    f"Dead-man's switch tripped for node '{device.device_name}' [{device.id}]. "
                                    f"No heartbeat received for {elapsed:.1f}s (threshold: {TIMEOUT_THRESHOLD_SECONDS:.1f}s)."
                                ),
                                created_at=now
                            )
                            db.add(timeout_alert)

                db.commit()
            except Exception as e:
                db.rollback()
                print(f"[Watchdog Daemon Error] {e}")
            finally:
                db.close()
        except asyncio.CancelledError:
            break


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB and seed default records
    init_db()
    monitor_task = asyncio.create_task(deadman_switch_monitor_loop())
    yield
    # Shutdown
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Cloud-Connected Smart Plant Care & Digital Twin Platform",
    description="Production-grade Cloud Ingestion, Industrial Control Law, and SITL Physics Pipeline.",
    version="2.0.0",
    lifespan=lifespan
)

# Cross-Origin Resource Sharing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static frontend assets
STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# -------------------------------------------------------------
# Cryptographic Edge Security & Authentication
# -------------------------------------------------------------
def verify_device_credentials(
    device: Device,
    raw_body: bytes,
    x_api_key: Optional[str],
    x_device_signature: Optional[str]
) -> bool:
    """
    Validates API key and verifies HMAC-SHA256 signature against edge pre-shared secret.
    """
    if not REQUIRE_HMAC_AUTH:
        return True

    # 1. API Key check
    if not x_api_key or x_api_key != device.api_key_hash:
        return False

    # 2. HMAC Signature verification
    if not x_device_signature or not device.hmac_secret:
        return False

    expected_signature = hmac.new(
        device.hmac_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, x_device_signature)


# -------------------------------------------------------------
# Health Score Calculation Helper
# -------------------------------------------------------------
def compute_health_score(device: Device, latest_reading: Optional[SensorReading]) -> float:
    """Calculates composite agronomic health index (0 to 100)."""
    if not latest_reading:
        return 100.0

    score = 100.0
    # Moisture penalties
    if latest_reading.soil_moisture < device.moisture_threshold_min:
        deficit = device.moisture_threshold_min - latest_reading.soil_moisture
        score -= min(40.0, deficit * 2.0)
    elif latest_reading.soil_moisture > device.moisture_threshold_max:
        surplus = latest_reading.soil_moisture - device.moisture_threshold_max
        score -= min(25.0, surplus * 1.5)

    # Temperature penalties
    if latest_reading.temperature > 35.0:
        score -= min(30.0, (latest_reading.temperature - 35.0) * 4.0)
    elif latest_reading.temperature < 15.0:
        score -= min(20.0, (15.0 - latest_reading.temperature) * 2.5)

    # Water tank penalty
    if latest_reading.water_tank_level < 15.0:
        score -= 20.0

    return max(0.0, round(score, 1))


# -------------------------------------------------------------
# REST API Endpoints
# -------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def serve_dashboard():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse({"message": "Smart Plant Care API operational. Dashboard available at /static/index.html."})


@app.get("/api/v1/health", response_model=HealthResponse, tags=["Monitoring"])
def health_probe(db: Session = Depends(get_db)):
    """Cloud readiness and liveness probe."""
    device_count = db.query(Device).count()
    return HealthResponse(
        status="HEALTHY",
        uptime_seconds=round(time.time() - START_TIME, 2),
        database="CONNECTED",
        active_devices_count=device_count,
        version="2.0.0"
    )


@app.post("/api/v1/telemetry/ingest", response_model=TelemetryIngestResponse, tags=["Edge Ingest"])
async def ingest_telemetry(
    request: Request,
    payload: TelemetryIngestRequest,
    x_api_key: Optional[str] = Header(None),
    x_device_signature: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Secure edge ingestion endpoint.
    Verifies cryptographic signature, stores telemetry, updates digital twin state,
    and runs the industrial hysteresis automation engine.
    """
    # Look up device shadow
    device = db.query(Device).filter(Device.id == payload.device_id).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edge device '{payload.device_id}' is not registered."
        )

    # Authenticate edge payload
    raw_body = await request.body()
    if not verify_device_credentials(device, raw_body, x_api_key, x_device_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cryptographic verification failed: Invalid x-api-key or x-device-signature HMAC."
        )

    now = datetime.datetime.utcnow()
    device.last_seen = now
    device.status = "ONLINE"

    # Persist time-series telemetry reading
    reading = SensorReading(
        device_id=device.id,
        soil_moisture=payload.soil_moisture,
        temperature=payload.temperature,
        humidity=payload.humidity,
        light_level=payload.light_level,
        water_tank_level=payload.water_tank_level,
        created_at=payload.timestamp if payload.timestamp else now
    )
    db.add(reading)

    # Execute industrial automation & hysteresis control
    decision = evaluate_telemetry(db, device, reading)
    db.commit()

    return TelemetryIngestResponse(
        status="INGESTED",
        decision=decision.trigger_type,
        pump_active=decision.should_water,
        pump_duration_seconds=decision.duration_seconds,
        reason=decision.reason,
        alerts_triggered=[a.alert_type for a in decision.alerts],
        server_timestamp=now
    )


@app.get("/api/v1/devices", response_model=List[DeviceResponse], tags=["Digital Twin"])
def list_devices(db: Session = Depends(get_db)):
    """List all registered edge nodes with active shadow state and health scores."""
    devices = db.query(Device).all()
    results = []
    now = datetime.datetime.utcnow()

    for d in devices:
        latest = (
            db.query(SensorReading)
            .filter(SensorReading.device_id == d.id)
            .order_by(desc(SensorReading.created_at))
            .first()
        )
        last_event = (
            db.query(WateringEvent)
            .filter(WateringEvent.device_id == d.id)
            .order_by(desc(WateringEvent.timestamp))
            .first()
        )

        # Check pump active state and cooldown countdown
        is_pump_active = False
        remaining_cooldown = 0

        if last_event:
            elapsed = (now - last_event.timestamp).total_seconds()
            if elapsed < last_event.duration_seconds:
                is_pump_active = True
            cooldown_total = d.cooldown_minutes * 60.0
            if elapsed < cooldown_total:
                remaining_cooldown = int(cooldown_total - elapsed)

        dev_res = DeviceResponse(
            id=d.id,
            device_name=d.device_name,
            plant_species=d.plant_species,
            moisture_threshold_min=d.moisture_threshold_min,
            moisture_threshold_max=d.moisture_threshold_max,
            pump_duration_seconds=d.pump_duration_seconds,
            cooldown_minutes=d.cooldown_minutes,
            last_seen=d.last_seen,
            status=d.status,
            health_score=compute_health_score(d, latest),
            active_pump=is_pump_active,
            cooldown_remaining_seconds=remaining_cooldown
        )
        results.append(dev_res)

    return results


@app.get("/api/v1/devices/{device_id}/latest", tags=["Digital Twin"])
def get_device_latest_state(device_id: str, db: Session = Depends(get_db)):
    """Return device shadow, current environmental metrics, pump state, and health."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    latest_reading = (
        db.query(SensorReading)
        .filter(SensorReading.device_id == device_id)
        .order_by(desc(SensorReading.created_at))
        .first()
    )

    last_event = (
        db.query(WateringEvent)
        .filter(WateringEvent.device_id == device_id)
        .order_by(desc(WateringEvent.timestamp))
        .first()
    )

    now = datetime.datetime.utcnow()
    is_pump_active = False
    cooldown_remaining = 0

    if last_event:
        elapsed = (now - last_event.timestamp).total_seconds()
        if elapsed < last_event.duration_seconds:
            is_pump_active = True
        total_cooldown = device.cooldown_minutes * 60.0
        if elapsed < total_cooldown:
            cooldown_remaining = int(total_cooldown - elapsed)

    return {
        "device": DeviceResponse(
            id=device.id,
            device_name=device.device_name,
            plant_species=device.plant_species,
            moisture_threshold_min=device.moisture_threshold_min,
            moisture_threshold_max=device.moisture_threshold_max,
            pump_duration_seconds=device.pump_duration_seconds,
            cooldown_minutes=device.cooldown_minutes,
            last_seen=device.last_seen,
            status=device.status,
            health_score=compute_health_score(device, latest_reading),
            active_pump=is_pump_active,
            cooldown_remaining_seconds=cooldown_remaining
        ),
        "latest_telemetry": latest_reading,
        "last_watering_event": last_event,
        "server_time": now
    }


@app.get("/api/v1/devices/{device_id}/history", response_model=DeviceHistoryResponse, tags=["Analytics"])
def get_device_history(
    device_id: str,
    hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db)
):
    """Aggregate time-series telemetry and watering occurrences for analytical visualization."""
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)

    readings = (
        db.query(SensorReading)
        .filter(SensorReading.device_id == device_id, SensorReading.created_at >= since)
        .order_by(SensorReading.created_at.asc())
        .limit(500)
        .all()
    )

    events = (
        db.query(WateringEvent)
        .filter(WateringEvent.device_id == device_id, WateringEvent.timestamp >= since)
        .order_by(WateringEvent.timestamp.asc())
        .all()
    )

    return DeviceHistoryResponse(
        device_id=device_id,
        readings=[SensorReadingResponse.model_validate(r) for r in readings],
        watering_events=[WateringEventResponse.model_validate(e) for e in events]
    )


@app.post("/api/v1/devices/{device_id}/actuate", response_model=ManualActuateResponse, tags=["Actuation"])
def actuate_irrigation(
    device_id: str,
    actuation: ManualActuateRequest,
    db: Session = Depends(get_db)
):
    """Manual remote irrigation trigger with authentication and cooldown verification."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    success, duration, message = validate_manual_actuation(db, device, actuation.duration_seconds)
    if not success:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=message)

    return ManualActuateResponse(
        success=True,
        message=message,
        duration_seconds=duration,
        cooldown_remaining_seconds=int(device.cooldown_minutes * 60.0)
    )


@app.put("/api/v1/devices/{device_id}/config", response_model=DeviceResponse, tags=["Configuration"])
def update_device_config(
    device_id: str,
    config: DeviceUpdate,
    db: Session = Depends(get_db)
):
    """Dynamically calibrate botanical thresholds, cooldown timeouts, and plant profile."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if config.device_name is not None:
        device.device_name = config.device_name
    if config.plant_species is not None:
        device.plant_species = config.plant_species
        # Auto-align preset if exact profile exists and fields weren't explicitly overridden
        profile = get_profile(config.plant_species)
        if config.moisture_threshold_min is None:
            device.moisture_threshold_min = profile["moisture_threshold_min"]
        if config.moisture_threshold_max is None:
            device.moisture_threshold_max = profile["moisture_threshold_max"]
        if config.pump_duration_seconds is None:
            device.pump_duration_seconds = profile["pump_duration_seconds"]
        if config.cooldown_minutes is None:
            device.cooldown_minutes = profile["cooldown_minutes"]

    if config.moisture_threshold_min is not None:
        device.moisture_threshold_min = config.moisture_threshold_min
    if config.moisture_threshold_max is not None:
        device.moisture_threshold_max = config.moisture_threshold_max
    if config.pump_duration_seconds is not None:
        device.pump_duration_seconds = config.pump_duration_seconds
    if config.cooldown_minutes is not None:
        device.cooldown_minutes = config.cooldown_minutes

    db.commit()
    db.refresh(device)

    return DeviceResponse(
        id=device.id,
        device_name=device.device_name,
        plant_species=device.plant_species,
        moisture_threshold_min=device.moisture_threshold_min,
        moisture_threshold_max=device.moisture_threshold_max,
        pump_duration_seconds=device.pump_duration_seconds,
        cooldown_minutes=device.cooldown_minutes,
        last_seen=device.last_seen,
        status=device.status,
        health_score=100.0,
        active_pump=False,
        cooldown_remaining_seconds=0
    )


@app.get("/api/v1/alerts", response_model=List[AlertResponse], tags=["Alarms"])
def get_alerts(
    unack_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Retrieve system alarms with optional filter for unacknowledged incidents."""
    query = db.query(Alert)
    if unack_only:
        query = query.filter(Alert.acknowledged == False)

    alerts = query.order_by(desc(Alert.created_at)).limit(limit).all()
    return [AlertResponse.model_validate(a) for a in alerts]


@app.put("/api/v1/alerts/{alert_id}/ack", tags=["Alarms"])
def acknowledge_alert(alert_id: str, db: Session = Depends(get_db)):
    """Acknowledge and silence an operational alarm."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert incident not found")

    alert.acknowledged = True
    db.commit()
    return {"status": "SUCCESS", "message": f"Alert {alert_id} acknowledged."}


@app.get("/api/v1/plant-profiles", tags=["Configuration"])
def fetch_plant_profiles():
    """Retrieve catalog of botanical profiles and presets."""
    return list_profiles()
