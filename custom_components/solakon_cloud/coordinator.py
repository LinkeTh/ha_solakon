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

    async def _async_optional_mode(
        self, device_id: str, aggregated: dict[str, Any]
    ) -> dict[str, Any] | None:
        if aggregated.get("supportsOperatingMode") is not True:
            return None
        return await self.client.async_get_mode(device_id)
