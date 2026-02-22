"""Dashboard schemas for request/response validation."""

from datetime import datetime

from pydantic import BaseModel, Field


# BART schemas

class BartStationPreference(BaseModel):
    """A single station preference within BART card config."""

    abbr: str = Field(..., description="Station abbreviation (e.g. EMBR)")
    platform: int | None = Field(None, description="Platform filter (1, 2, etc.) or null for all")


class BartEstimate(BaseModel):
    """A single departure estimate."""

    destination: str
    abbreviation: str
    minutes: str  # Can be "Leaving" or a number
    platform: str
    direction: str
    color: str
    hex_color: str
    length: str
    delay: str


class BartDepartureResponse(BaseModel):
    """Response for a station's departures."""

    station_name: str
    station_abbr: str
    estimates: list[BartEstimate]
    fetched_at: datetime


class BartStation(BaseModel):
    """A BART station."""

    name: str
    abbr: str
    city: str
    county: str
    latitude: float
    longitude: float


class BartStationsResponse(BaseModel):
    """Response for station list."""

    stations: list[BartStation]


# Dashboard preference schemas

class DashboardPreferenceUpdate(BaseModel):
    """Schema for creating/updating a dashboard card preference."""

    preferences: dict
    sort_order: int = 0


class DashboardPreferenceResponse(BaseModel):
    """Schema for a dashboard card preference response."""

    model_config = {"from_attributes": True}

    id: str
    card_type: str
    preferences: dict
    sort_order: int
    created_at: datetime
    updated_at: datetime


class DashboardPreferenceList(BaseModel):
    """List of dashboard preferences."""

    items: list[DashboardPreferenceResponse]


# Feature access schemas

class FeatureAccessUpdate(BaseModel):
    """Schema for setting feature access."""

    enabled: bool


class FeatureAccessResponse(BaseModel):
    """Schema for feature access response."""

    model_config = {"from_attributes": True}

    id: str
    user_id: str
    feature_key: str
    enabled: bool
    granted_by: str | None
    created_at: datetime
    updated_at: datetime


# Admin schemas

class AdminUserResponse(BaseModel):
    """User info for admin listing."""

    model_config = {"from_attributes": True}

    id: str
    email: str
    role: str
    created_at: datetime


class AdminUserList(BaseModel):
    """List of users for admin."""

    items: list[AdminUserResponse]


class RoleUpdate(BaseModel):
    """Schema for updating a user's role."""

    role: str = Field(..., pattern="^(admin|user)$")
