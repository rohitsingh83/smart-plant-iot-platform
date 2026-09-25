"""
Pydantic v2 Contract Specifications
Strict data validation, edge serialization, and cloud payload schemas.
"""

from typing import List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict
import datetime


class TelemetryIngestRequest(BaseModel):
    device_id: str = Field(..., description="Unique hardware or virtual edge identifier")
    soil_moisture: float = Field(..., ge=0.0, le=100.0, description="Volumetric or calibrated soil moisture percentage")
    temperature: float = Field(..., ge=-20.0, le=70.0, description="Ambient air temperature in Celsius")
    humidity: float = Field(..., ge=0.0, le=100.0, description="Relative atmospheric humidity percentage")
    light_level: float = Field(..., ge=0.0, le=150000.0, description="Ambient illuminance in Lux")
    water_tank_level: float = Field(..., ge=0.0, le=100.0, description="Reservoir liquid level percentage")
    timestamp: Optional[datetime.datetime] = Field(default=None, description="Edge observation timestamp")

    model_config = ConfigDict(from_attributes=True)


class TelemetryIngestResponse(BaseModel):
    status: str
    decision: str
    pump_active: bool
    pump_duration_seconds: float
    reason: str
    alerts_triggered: List[str]
    server_timestamp: datetime.datetime


class DeviceBase(BaseModel):
    device_name: str
    plant_species: str
    moisture_threshold_min: float = Field(ge=5.0, le=90.0)
    moisture_threshold_max: float = Field(ge=10.0, le=98.0)
    pump_duration_seconds: float = Field(ge=1.0, le=15.0)
    cooldown_minutes: float = Field(ge=1.0, le=720.0)


class DeviceUpdate(BaseModel):
    device_name: Optional[str] = None
    plant_species: Optional[str] = None
    moisture_threshold_min: Optional[float] = None
    moisture_threshold_max: Optional[float] = None
    pump_duration_seconds: Optional[float] = None
    cooldown_minutes: Optional[float] = None


class DeviceResponse(DeviceBase):
    id: str
    status: str
    last_seen: datetime.datetime
    health_score: float = Field(default=100.0, description="Calculated plant wellness score (0-100)")
    active_pump: bool = False
    cooldown_remaining_seconds: int = 0

    model_config = ConfigDict(from_attributes=True)


class SensorReadingResponse(BaseModel):
    id: str
    device_id: str
    soil_moisture: float
    temperature: float
    humidity: float
    light_level: float
    water_tank_level: float
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class WateringEventResponse(BaseModel):
    id: str
    device_id: str
    trigger_type: str
    duration_seconds: float
    moisture_before: float
    moisture_after: Optional[float] = None
    timestamp: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class ManualActuateRequest(BaseModel):
    duration_seconds: Optional[float] = Field(default=None, ge=1.0, le=10.0)
    reason: Optional[str] = "Manual remote trigger via dashboard"


class ManualActuateResponse(BaseModel):
    success: bool
    message: str
    duration_seconds: float
    cooldown_remaining_seconds: int


class AlertResponse(BaseModel):
    id: str
    device_id: str
    severity: str
    alert_type: str
    message: str
    acknowledged: bool
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class DeviceHistoryResponse(BaseModel):
    device_id: str
    readings: List[SensorReadingResponse]
    watering_events: List[WateringEventResponse]


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    database: str
    active_devices_count: int
    version: str
