"""Base entity for Solakon Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SolakonCloudCoordinator


class SolakonCloudEntity(CoordinatorEntity[SolakonCloudCoordinator]):
    """Base entity tied to one Solakon inverter."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SolakonCloudCoordinator, device_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id

    @property
    def _device_payload(self) -> dict[str, Any]:
        return self.coordinator.data["devices"][self._device_id]

    @property
    def available(self) -> bool:
        return super().available and self._device_id in self.coordinator.data["devices"]

    @property
    def device_info(self) -> DeviceInfo:
        metadata = self._device_payload["metadata"]
        aggregated = self._device_payload["aggregated"]
        label = (
            metadata.get("label")
            or aggregated.get("label")
            or metadata.get("name")
            or f"Solakon {self._device_id[-6:]}"
        )
        model = (
            aggregated.get("model")
            or metadata.get("hardwareDeviceType")
            or metadata.get("model")
            or "Inverter"
        )
        manufacturer = metadata.get("manufacturer") or "Solakon"
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=str(label),
            manufacturer=str(manufacturer),
            model=str(model),
            serial_number=self._device_id,
        )
