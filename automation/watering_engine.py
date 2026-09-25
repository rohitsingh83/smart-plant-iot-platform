"""
Industrial Automation & Hydrological Control Engine
Implements Dual-Threshold Hysteresis, Lockout Timers, Watchdog Guardrails, and Anomaly Detection.
"""

import datetime
from typing import Tuple, List, Optional
from sqlalchemy.orm import Session
from cloud.database import Device, SensorReading, WateringEvent, Alert

# Hard safety constraints
MAX_WATCHDOG_RUNTIME_SECONDS = 8.0
MIN_TANK_OPERATING_LEVEL = 10.0
HIGH_TEMP_THRESHOLD = 38.0
CRITICAL_MOISTURE_THRESHOLD = 10.0


class AutomationDecision:
    def __init__(
        self,
        should_water: bool,
        duration_seconds: float,
        trigger_type: str,
        reason: str,
        alerts: List[Alert]
    ):
        self.should_water = should_water
        self.duration_seconds = duration_seconds
        self.trigger_type = trigger_type
        self.reason = reason
        self.alerts = alerts


def evaluate_telemetry(
    db: Session,
    device: Device,
    reading: SensorReading
) -> AutomationDecision:
    """
    Evaluates newly ingested telemetry against control laws and botanical safety envelopes.
    Returns actuation decision and logs alerts / watering events in the database session.
    """
    alerts: List[Alert] = []
    now = datetime.datetime.utcnow()

    # 1. Environmental Anomaly Diagnostics
    if reading.temperature >= HIGH_TEMP_THRESHOLD:
        high_temp_alert = Alert(
            device_id=device.id,
            severity="WARNING" if reading.temperature < 42.0 else "CRITICAL",
            alert_type="HIGH_TEMP",
            message=f"Elevated thermal spike detected: {reading.temperature:.1f}°C exceeds threshold of {HIGH_TEMP_THRESHOLD}°C.",
            created_at=now
        )
        db.add(high_temp_alert)
        alerts.append(high_temp_alert)

    if reading.soil_moisture <= CRITICAL_MOISTURE_THRESHOLD:
        severe_drought_alert = Alert(
            device_id=device.id,
            severity="CRITICAL",
            alert_type="LOW_MOISTURE",
            message=f"Critical root desiccation: soil moisture at {reading.soil_moisture:.1f}% is beneath emergency threshold of {CRITICAL_MOISTURE_THRESHOLD}%.",
            created_at=now
        )
        db.add(severe_drought_alert)
        alerts.append(severe_drought_alert)

    # 2. Reservoir Safety Guardrail
    if reading.water_tank_level < MIN_TANK_OPERATING_LEVEL:
        tank_empty_alert = Alert(
            device_id=device.id,
            severity="CRITICAL",
            alert_type="TANK_EMPTY",
            message=f"Reservoir depletion: Tank level is {reading.water_tank_level:.1f}%. Submersible pump locked to prevent dry-run cavitation.",
            created_at=now
        )
        db.add(tank_empty_alert)
        alerts.append(tank_empty_alert)
        # Lockout pump immediately
        return AutomationDecision(
            should_water=False,
            duration_seconds=0.0,
            trigger_type="NONE",
            reason=f"Water reservoir level ({reading.water_tank_level:.1f}%) is below minimum safety limit ({MIN_TANK_OPERATING_LEVEL}%).",
            alerts=alerts
        )

    # 3. Hysteresis Evaluation: Moisture <= Lower Threshold Bound
    if reading.soil_moisture <= device.moisture_threshold_min:
        # Check Cooldown Window against last watering event
        last_event = (
            db.query(WateringEvent)
            .filter(WateringEvent.device_id == device.id)
            .order_by(WateringEvent.timestamp.desc())
            .first()
        )

        if last_event:
            elapsed_seconds = (now - last_event.timestamp).total_seconds()
            required_cooldown_seconds = device.cooldown_minutes * 60.0

            if elapsed_seconds < required_cooldown_seconds:
                remaining_cooldown = int(required_cooldown_seconds - elapsed_seconds)
                return AutomationDecision(
                    should_water=False,
                    duration_seconds=0.0,
                    trigger_type="NONE",
                    reason=f"Irrigation throttled by anti-flapping cooldown. {remaining_cooldown}s remaining of {int(required_cooldown_seconds)}s lockout.",
                    alerts=alerts
                )

        # Fail-Safe Watchdog clamp on duration
        actuation_time = min(device.pump_duration_seconds, MAX_WATCHDOG_RUNTIME_SECONDS)

        # Record Watering Event
        event = WateringEvent(
            device_id=device.id,
            trigger_type="AUTOMATIC_HYSTERESIS",
            duration_seconds=actuation_time,
            moisture_before=reading.soil_moisture,
            timestamp=now
        )
        db.add(event)

        return AutomationDecision(
            should_water=True,
            duration_seconds=actuation_time,
            trigger_type="AUTOMATIC_HYSTERESIS",
            reason=f"Moisture ({reading.soil_moisture:.1f}%) <= Min Threshold ({device.moisture_threshold_min:.1f}%). Automated pulse issued for {actuation_time:.1f}s.",
            alerts=alerts
        )

    # Upper hysteresis bound: Soil Moisture is above target
    if reading.soil_moisture >= device.moisture_threshold_max:
        return AutomationDecision(
            should_water=False,
            duration_seconds=0.0,
            trigger_type="NONE",
            reason=f"Soil moisture ({reading.soil_moisture:.1f}%) satisfies target saturation threshold ({device.moisture_threshold_max:.1f}%).",
            alerts=alerts
        )

    # In-band hysteresis stabilization
    return AutomationDecision(
        should_water=False,
        duration_seconds=0.0,
        trigger_type="NONE",
        reason=f"Moisture ({reading.soil_moisture:.1f}%) is within deadband [{device.moisture_threshold_min:.1f}%, {device.moisture_threshold_max:.1f}%]. Pump idle.",
        alerts=alerts
    )


def validate_manual_actuation(
    db: Session,
    device: Device,
    requested_duration: Optional[float] = None
) -> Tuple[bool, float, str]:
    """
    Validates a manual operator override request, enforcing cooldown and watchdog limits.
    """
    now = datetime.datetime.utcnow()
    last_event = (
        db.query(WateringEvent)
        .filter(WateringEvent.device_id == device.id)
        .order_by(WateringEvent.timestamp.desc())
        .first()
    )

    if last_event:
        elapsed = (now - last_event.timestamp).total_seconds()
        cooldown_sec = device.cooldown_minutes * 60.0
        if elapsed < cooldown_sec:
            remaining = int(cooldown_sec - elapsed)
            return False, 0.0, f"Manual actuation blocked: Device is in mandatory cooldown ({remaining}s remaining)."

    # Enforce watchdog maximum
    duration = min(
        requested_duration if (requested_duration and requested_duration > 0) else device.pump_duration_seconds,
        MAX_WATCHDOG_RUNTIME_SECONDS
    )

    # Get latest reading for baseline
    latest_reading = (
        db.query(SensorReading)
        .filter(SensorReading.device_id == device.id)
        .order_by(SensorReading.created_at.desc())
        .first()
    )
    moisture_before = latest_reading.soil_moisture if latest_reading else 50.0

    event = WateringEvent(
        device_id=device.id,
        trigger_type="MANUAL_OVERRIDE",
        duration_seconds=duration,
        moisture_before=moisture_before,
        timestamp=now
    )
    db.add(event)
    db.commit()

    return True, duration, f"Manual irrigation pulse approved for {duration:.1f} seconds."
