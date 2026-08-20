"""Data coordinator for Solakon Cloud."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    SolakonApiClient,
    SolakonAuthError,
    SolakonConnectionError,
    SolakonError,
)
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class SolakonCloudCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch account devices and their latest measurements."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SolakonApiClient,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            metadata = await self.client.async_get_inverters()
            if not metadata:
                raise UpdateFailed("No inverter was returned by the Solakon account")

            results = await asyncio.gather(
                *(self._async_device_data(device) for device in metadata),
                return_exceptions=True,
            )
        except SolakonAuthError as err:
            raise ConfigEntryAuthFailed from err
        except SolakonConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except SolakonError as err:
            raise UpdateFailed(str(err)) from err

        devices: dict[str, dict[str, Any]] = {}
        errors: list[Exception] = []
        for device, result in zip(metadata, results, strict=True):
            device_id = device["deviceId"]
            if isinstance(result, Exception):
                errors.append(result)
                continue
            devices[device_id] = result

        if not devices:
            if errors and isinstance(errors[0], SolakonAuthError):
                raise ConfigEntryAuthFailed from errors[0]
            raise UpdateFailed(str(errors[0]) if errors else "No inverter data available")
        return {"devices": devices}

    async def _async_device_data(self, metadata: dict[str, Any]) -> dict[str, Any]:
        device_id = metadata["deviceId"]
        aggregated = await self.client.async_get_aggregated(device_id)

        # Debug Logging: rohen API-Wert protokollieren, bevor die
        # Bereinigung greift, damit man beide Zustände vergleichen kann.
        _LOGGER.debug(
            "Solakon raw realtimeData for %s: today=%s totalLifetime=%s timestamp=%s",
            device_id,
            aggregated.get("realtimeData", {}).get("today"),
            aggregated.get("realtimeData", {}).get("totalLifetime"),
            aggregated.get("realtimeData", {}).get("timestamp"),
        )

        aggregated = self._sanitize_today(device_id, aggregated)

        maximum_power, mode = await asyncio.gather(
            self.client.async_get_maximum_power(device_id),
            self._async_optional_mode(device_id, aggregated),
        )
        return {
            "metadata": metadata,
            "aggregated": aggregated,
            "maximum_power": maximum_power,
            "mode": mode,
        }

    def _sanitize_today(
        self, device_id: str, aggregated: dict[str, Any]
    ) -> dict[str, Any]:
        """Guard against a bogus 'today' value on the first poll after a reconnect."""
        realtime = aggregated.get("realtimeData")
        if not isinstance(realtime, dict):
            return aggregated

        today = realtime.get("today")
        total = realtime.get("totalLifetime")
        if today is None or total is None:
            return aggregated

        try:
            today_f, total_f = float(today), float(total)
        except (TypeError, ValueError):
            return aggregated

        previous_devices = (self.data or {}).get("devices", {})
        previous_today = None
        if device_id in previous_devices:
            prev_realtime = previous_devices[device_id]["aggregated"].get(
                "realtimeData", {}
            )
            try:
                previous_today = float(prev_realtime.get("today"))
            except (TypeError, ValueError):
                previous_today = None

        is_suspicious = total_f > 0 and abs(today_f - total_f) < max(
            0.05, total_f * 0.01
        )

        if is_suspicious and (previous_today is None or today_f > previous_today + 5):
            _LOGGER.warning(
                "Solakon %s: verworfener Ausreißer bei energy_today (%.3f kWh "
                "≈ energy_total %.3f kWh) – wahrscheinlich stale API-Antwort "
                "nach Reconnect. Verwende vorherigen Wert (%s).",
                device_id,
                today_f,
                total_f,
                previous_today,
            )
            realtime = dict(realtime)
            realtime["today"] = previous_today if previous_today is not None else 0.0
            aggregated = dict(aggregated)
            aggregated["realtimeData"] = realtime

        return aggregated

    async def _async_optional_mode(
        self, device_id: str, aggregated: dict[str, Any]
    ) -> dict[str, Any] | None:
        if aggregated.get("supportsOperatingMode") is not True:
            return None
        return await self.client.async_get_mode(device_id)
