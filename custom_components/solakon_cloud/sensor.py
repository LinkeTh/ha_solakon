"""Sensors for Solakon Cloud inverter telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import SolakonCloudConfigEntry
from .coordinator import SolakonCloudCoordinator
from .entity import SolakonCloudEntity


def _path(payload: dict[str, Any], *parts: str) -> Any:
    value: Any = payload
    for part in parts:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # Solakon currently returns local wall-clock timestamps without an
        # offset for this device. Home Assistant requires timezone-aware values.
        parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return parsed


def _lifetime(payload: dict[str, Any]) -> float | None:
    raw = _number(_path(payload, "realtimeData", "totalLifetime"))
    if raw is None:
        return None
    return raw + (_number(payload.get("additionalSummaryKwh")) or 0)


@dataclass(frozen=True, kw_only=True)
class SolakonSensorDescription(SensorEntityDescription):
    """Describe a Solakon sensor value."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[SolakonSensorDescription, ...] = (
    SolakonSensorDescription(
        key="current_power",
        translation_key="current_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p: _number(_path(p, "realtimeData", "currentPower")),
    ),
    SolakonSensorDescription(
        key="energy_today",
        translation_key="energy_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda p: _number(_path(p, "realtimeData", "today")),
    ),
    SolakonSensorDescription(
        key="energy_total",
        translation_key="energy_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_lifetime,
    ),
    SolakonSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p: _number(_path(p, "microInverterInfo", "temperature")),
    ),
    SolakonSensorDescription(
        key="ac_voltage",
        translation_key="ac_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p: _number(_path(p, "microInverterInfo", "ac", "voltage")),
    ),
    SolakonSensorDescription(
        key="ac_current",
        translation_key="ac_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p: _number(_path(p, "microInverterInfo", "ac", "current")),
    ),
    SolakonSensorDescription(
        key="ac_power",
        translation_key="ac_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p: _number(_path(p, "microInverterInfo", "ac", "power")),
    ),
    SolakonSensorDescription(
        key="ac_frequency",
        translation_key="ac_frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p: _number(_path(p, "microInverterInfo", "ac", "frequency")),
    ),
    SolakonSensorDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda p: _number(_path(p, "wifiData", "signal")),
    ),
    SolakonSensorDescription(
        key="last_update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda p: _timestamp(_path(p, "realtimeData", "timestamp")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolakonCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors that are present in the first payload."""
    coordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = []
    for device_id, device in coordinator.data["devices"].items():
        aggregated = device["aggregated"]
        entities.extend(
            SolakonSensor(coordinator, device_id, description)
            for description in SENSORS
            if description.value_fn(aggregated) is not None
        )

        pv_rows = _path(aggregated, "microInverterInfo", "pv")
        if isinstance(pv_rows, list):
            for list_index, row in enumerate(pv_rows):
                if not isinstance(row, dict):
                    continue
                pv_index = row.get("index", list_index + 1)
                for field, unit, device_class in (
                    ("voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
                    ("current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
                    ("power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER),
                ):
                    if _number(row.get(field)) is None:
                        continue
                    entities.append(
                        SolakonPvSensor(
                            coordinator,
                            device_id,
                            int(pv_index),
                            field,
                            unit,
                            device_class,
                        )
                    )
    async_add_entities(entities)


class SolakonSensor(SolakonCloudEntity, SensorEntity):
    """A scalar inverter sensor."""

    entity_description: SolakonSensorDescription

    def __init__(
        self,
        coordinator: SolakonCloudCoordinator,
        device_id: str,
        description: SolakonSensorDescription,
    ) -> None:
        super().__init__(coordinator, device_id)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self._device_payload["aggregated"])


class SolakonPvSensor(SolakonCloudEntity, SensorEntity):
    """One voltage/current/power value for a PV input."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: SolakonCloudCoordinator,
        device_id: str,
        pv_index: int,
        field: str,
        unit: str,
        device_class: SensorDeviceClass,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._pv_index = pv_index
        self._field = field
        self._attr_unique_id = f"{device_id}_pv_{pv_index}_{field}"
        self._attr_name = f"PV{pv_index} {field.capitalize()}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class

    @property
    def native_value(self) -> float | None:
        pv_rows = _path(
            self._device_payload["aggregated"], "microInverterInfo", "pv"
        )
        if not isinstance(pv_rows, list):
            return None
        for list_index, row in enumerate(pv_rows):
            if not isinstance(row, dict):
                continue
            try:
                row_index = int(row.get("index", list_index + 1))
            except (TypeError, ValueError):
                continue
            if row_index == self._pv_index:
                return _number(row.get(self._field))
        return None
