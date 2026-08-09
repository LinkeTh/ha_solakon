"""Operating mode control for Solakon Cloud."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SolakonCloudConfigEntry
from .coordinator import SolakonCloudCoordinator
from .entity import SolakonCloudEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolakonCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Only create the switch if Solakon declares operating-mode support."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        SolakonOperatingModeSwitch(coordinator, device_id)
        for device_id, data in coordinator.data["devices"].items()
        if data["aggregated"].get("supportsOperatingMode") is True
        and isinstance(data.get("mode"), dict)
    )


class SolakonOperatingModeSwitch(SolakonCloudEntity, SwitchEntity):
    """The B2500/battery operating-mode toggle exposed by Solakon."""

    _attr_translation_key = "b2500_mode"
    _attr_icon = "mdi:battery-sync"

    def __init__(self, coordinator: SolakonCloudCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_b2500_mode"

    @property
    def is_on(self) -> bool:
        payload = self._device_payload.get("mode")
        return isinstance(payload, dict) and int(payload.get("mode", 0)) == 1

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.client.async_set_mode(self._device_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.client.async_set_mode(self._device_id, False)
        await self.coordinator.async_request_refresh()
