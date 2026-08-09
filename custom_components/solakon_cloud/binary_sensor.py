"""Binary sensors for Solakon Cloud."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Set up connectivity sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        SolakonOnlineBinarySensor(coordinator, device_id)
        for device_id in coordinator.data["devices"]
    )


class SolakonOnlineBinarySensor(SolakonCloudEntity, BinarySensorEntity):
    """Whether Solakon reports the inverter online."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "online"

    def __init__(self, coordinator: SolakonCloudCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_online"

    @property
    def is_on(self) -> bool:
        realtime = self._device_payload["aggregated"].get("realtimeData", {})
        return (
            realtime.get("currentStatus") == "active"
            or realtime.get("currentConnection") == "active"
        )

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        realtime = self._device_payload["aggregated"].get("realtimeData", {})
        return {"status_unknown_reason": realtime.get("statusUnknownReason")}
