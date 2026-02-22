"""BART API service with Redis caching."""

import json
import logging
from datetime import datetime, UTC

import httpx

from app.core.config import get_settings
from app.core.redis import get_redis
from app.schemas.dashboard import (
    BartDepartureResponse,
    BartEstimate,
    BartStation,
    BartStationsResponse,
)

logger = logging.getLogger(__name__)

BART_API_BASE = "https://api.bart.gov/api"
DEPARTURES_CACHE_TTL = 30  # seconds
STATIONS_CACHE_TTL = 86400  # 24 hours


class BartService:
    """Service for fetching BART real-time data with Redis caching."""

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.bart_api_key

    async def _get_cached(self, key: str) -> dict | None:
        """Try to get a cached value from Redis."""
        try:
            redis = await get_redis()
            cached = await redis.get(key)
            if cached:
                return json.loads(cached)
        except Exception:
            logger.debug("Redis cache miss or unavailable for key %s", key)
        return None

    async def _set_cached(self, key: str, value: dict, ttl: int) -> None:
        """Set a cached value in Redis."""
        try:
            redis = await get_redis()
            await redis.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception:
            logger.debug("Failed to set Redis cache for key %s", key)

    async def get_departures(
        self, station: str, platform: int | None = None
    ) -> BartDepartureResponse:
        """Get real-time departures for a station."""
        cache_key = f"bart:etd:{station}:{platform or 'all'}"
        cached = await self._get_cached(cache_key)
        if cached:
            return BartDepartureResponse(**cached)

        params: dict[str, str] = {
            "cmd": "etd",
            "orig": station.upper(),
            "key": self.api_key,
            "json": "y",
        }
        if platform is not None:
            params["plat"] = str(platform)

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BART_API_BASE}/etd.aspx", params=params)
            resp.raise_for_status()
            data = resp.json()

        root = data.get("root", {})
        station_list = root.get("station", [])

        estimates: list[BartEstimate] = []
        station_name = station.upper()
        station_abbr = station.upper()

        if station_list:
            stn = station_list[0]
            station_name = stn.get("name", station_name)
            station_abbr = stn.get("abbr", station_abbr)

            for etd in stn.get("etd", []):
                destination = etd.get("destination", "")
                abbreviation = etd.get("abbreviation", "")
                for est in etd.get("estimate", []):
                    estimates.append(
                        BartEstimate(
                            destination=destination,
                            abbreviation=abbreviation,
                            minutes=est.get("minutes", ""),
                            platform=est.get("platform", ""),
                            direction=est.get("direction", ""),
                            color=est.get("color", ""),
                            hex_color=est.get("hexcolor", ""),
                            length=est.get("length", ""),
                            delay=est.get("delay", "0"),
                        )
                    )

        result = BartDepartureResponse(
            station_name=station_name,
            station_abbr=station_abbr,
            estimates=estimates,
            fetched_at=datetime.now(UTC),
        )

        await self._set_cached(cache_key, result.model_dump(), DEPARTURES_CACHE_TTL)
        return result

    async def get_stations(self) -> BartStationsResponse:
        """Get list of all BART stations."""
        cache_key = "bart:stations"
        cached = await self._get_cached(cache_key)
        if cached:
            return BartStationsResponse(**cached)

        params = {
            "cmd": "stns",
            "key": self.api_key,
            "json": "y",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BART_API_BASE}/stn.aspx", params=params)
            resp.raise_for_status()
            data = resp.json()

        root = data.get("root", {})
        stations_data = root.get("stations", {}).get("station", [])

        stations = [
            BartStation(
                name=s.get("name", ""),
                abbr=s.get("abbr", ""),
                city=s.get("city", ""),
                county=s.get("county", ""),
                latitude=float(s.get("gtfs_latitude", 0)),
                longitude=float(s.get("gtfs_longitude", 0)),
            )
            for s in stations_data
        ]

        result = BartStationsResponse(stations=stations)
        await self._set_cached(cache_key, result.model_dump(), STATIONS_CACHE_TTL)
        return result
