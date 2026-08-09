"""Solakon Cloud prototype integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SolakonApiClient, SolakonTokens
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    PLATFORMS,
)
from .coordinator import SolakonCloudCoordinator


@dataclass(slots=True)
class SolakonCloudRuntimeData:
    """Runtime objects for a config entry."""

    client: SolakonApiClient
    coordinator: SolakonCloudCoordinator


type SolakonCloudConfigEntry = ConfigEntry[SolakonCloudRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant, entry: SolakonCloudConfigEntry
) -> bool:
    """Set up Solakon Cloud from a config entry."""

    async def save_tokens(tokens: SolakonTokens) -> None:
        data: dict[str, Any] = {
            **entry.data,
            CONF_ACCESS_TOKEN: tokens.access_token,
            CONF_REFRESH_TOKEN: tokens.refresh_token,
            CONF_EXPIRES_AT: tokens.expires_at,
        }
        hass.config_entries.async_update_entry(entry, data=data)

    try:
        tokens = SolakonTokens(
            access_token=entry.data[CONF_ACCESS_TOKEN],
            refresh_token=entry.data[CONF_REFRESH_TOKEN],
            expires_at=float(entry.data[CONF_EXPIRES_AT]),
        )
    except (KeyError, TypeError, ValueError) as err:
        raise ConfigEntryNotReady("Solakon session data is incomplete") from err

    client = SolakonApiClient(
        async_get_clientsession(hass), tokens=tokens, token_callback=save_tokens
    )
    coordinator = SolakonCloudCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = SolakonCloudRuntimeData(client, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SolakonCloudConfigEntry
) -> bool:
    """Unload a Solakon Cloud entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant, entry: SolakonCloudConfigEntry
) -> None:
    """Reload after entry options change."""
    await hass.config_entries.async_reload(entry.entry_id)
