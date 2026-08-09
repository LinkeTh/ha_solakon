"""Maximum inverter power control for Solakon Cloud."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfPower
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
    """Only create the control when Solakon exposes its endpoint."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        SolakonMaximumPowerNumber(coordinator, device_id)
        for device_id, data in coordinator.data["devices"].items()
        if isinstance(data.get("maximum_power"), dict)
        and data["maximum_power"].get("currentMaximumPower") is not None
    )


class SolakonMaximumPowerNumber(SolakonCloudEntity, NumberEntity):
    """Maximum AC output accepted by the inverter."""

    _attr_translation_key = "maximum_power"
    _attr_native_min_value = 0
    _attr_native_max_value = 800
    _attr_native_step = 100
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:flash"

    def __init__(self, coordinator: SolakonCloudCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_maximum_power"

    @property
    def native_value(self) -> float | None:
        payload = self._device_payload.get("maximum_power")
        if not isinstance(payload, dict):
            return None
        value = payload.get("currentMaximumPower")
        return float(value) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.async_set_maximum_power(
            self._device_id, int(value)
        )
        await self.coordinator.async_request_refresh()
