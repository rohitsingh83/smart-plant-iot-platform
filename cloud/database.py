"""
Cloud Database Architecture & Time-Series Telemetry Store
Compatible with SQLite (local development) and PostgreSQL / TimescaleDB (production cloud).
"""

import os
import uuid
import datetime
from typing import Generator
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./plant_care.db")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class User(Base):
    """Platform Tenant / User Model"""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    devices = relationship("Device", back_populates="owner", cascade="all, delete-orphan")


class Device(Base):
    """
    Physical Node / Digital Twin Shadow Record
    Tracks device metadata, botanical threshold configuration, and online liveness status.
    """
    __tablename__ = "devices"

    id = Column(String(64), primary_key=True, index=True)  # Hardware MAC, UUID, or edge ID
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    device_name = Column(String(100), nullable=False, default="Greenhouse Node 1")
    plant_species = Column(String(100), nullable=False, default="Tropical Foliage")
    moisture_threshold_min = Column(Float, nullable=False, default=40.0)  # Lower trigger bound
    moisture_threshold_max = Column(Float, nullable=False, default=70.0)  # Upper hysteresis target
    pump_duration_seconds = Column(Float, nullable=False, default=5.0)
    cooldown_minutes = Column(Float, nullable=False, default=30.0)
    last_seen = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    status = Column(String(20), nullable=False, default="ONLINE")  # ONLINE, OFFLINE, WARNING
    api_key_hash = Column(String(64), nullable=True)
    hmac_secret = Column(String(128), nullable=True)

    owner = relationship("User", back_populates="devices")
    readings = relationship("SensorReading", back_populates="device", cascade="all, delete-orphan")
    watering_events = relationship("WateringEvent", back_populates="device", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="device", cascade="all, delete-orphan")


class SensorReading(Base):
    """
    Time-Series Ingestion Telemetry Model
    Captures environmental and physical root-zone conditions with composite indexes for time-range analytical slicing.
    """
    __tablename__ = "sensor_readings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(64), ForeignKey("devices.id"), nullable=False, index=True)
    soil_moisture = Column(Float, nullable=False)        # % (0.0 to 100.0)
    temperature = Column(Float, nullable=False)          # Celsius
    humidity = Column(Float, nullable=False)             # % (0.0 to 100.0)
    light_level = Column(Float, nullable=False)          # Lux / Normalized light index
    water_tank_level = Column(Float, nullable=False)     # % (0.0 to 100.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)

    device = relationship("Device", back_populates="readings")

    __table_args__ = (
        Index("idx_device_created_at_desc", "device_id", created_at.desc()),
    )


class WateringEvent(Base):
    """
    Actuator Pulse & Irrigation Audit Log
    Records both automated hysteresis actions and manual remote overrides with pre/post deltas.
    """
    __tablename__ = "watering_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(64), ForeignKey("devices.id"), nullable=False, index=True)
    trigger_type = Column(String(32), nullable=False)   # AUTOMATIC_HYSTERESIS, MANUAL_OVERRIDE, SCHEDULED
    duration_seconds = Column(Float, nullable=False)
    moisture_before = Column(Float, nullable=False)
    moisture_after = Column(Float, nullable=True)       # Updated after hydration window
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)

    device = relationship("Device", back_populates="watering_events")


class Alert(Base):
    """
    Industrial Alarm & Operational Incident Model
    """
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(64), ForeignKey("devices.id"), nullable=False, index=True)
    severity = Column(String(20), nullable=False)       # INFO, WARNING, CRITICAL
    alert_type = Column(String(50), nullable=False)     # LOW_MOISTURE, HIGH_TEMP, TANK_EMPTY, DEVICE_TIMEOUT
    message = Column(Text, nullable=False)
    acknowledged = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)

    device = relationship("Device", back_populates="alerts")


def get_db() -> Generator[Session, None, None]:
    """Dependency injector yielding a database session per HTTP request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize relational schema and seed default device if missing."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        default_device_id = os.getenv("DEFAULT_DEVICE_ID", "esp32-greenhouse-01")
        existing_device = db.query(Device).filter(Device.id == default_device_id).first()
        if not existing_device:
            default_device = Device(
                id=default_device_id,
                device_name="Apex Greenhouse Node Alpha",
                plant_species="Tropical Foliage",
                moisture_threshold_min=45.0,
                moisture_threshold_max=75.0,
                pump_duration_seconds=5.0,
                cooldown_minutes=20.0,
                last_seen=datetime.datetime.utcnow(),
                status="ONLINE",
                api_key_hash=os.getenv("DEFAULT_API_KEY", "plant-care-edge-token-2026-secure"),
                hmac_secret=os.getenv("DEFAULT_HMAC_SECRET", "hmac-secret-key-plant-guard-99228811"),
            )
            db.add(default_device)
            db.commit()
    finally:
        db.close()
