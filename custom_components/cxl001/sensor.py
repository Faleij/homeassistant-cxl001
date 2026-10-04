"""Temperature sensor for a CXL001 / CXL001-C probe."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import CXLCoordinator
from .entity import CXLProbeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add one internal temperature sensor per probe id."""
    coordinator: CXLCoordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def _on_probe(probe_id: str) -> None:
        if probe_id in added:
            return
        added.add(probe_id)
        async_add_entities([CXLInternalTemperatureSensor(coordinator, probe_id)])

    if coordinator.data is not None:
        for probe_id in coordinator.data.probes:
            _on_probe(probe_id)
    entry.async_on_unload(coordinator.async_add_probe_listener(_on_probe))


class CXLInternalTemperatureSensor(CXLProbeEntity, SensorEntity):
    """The probe's single internal temperature.

    Same shape as the Meater BLE meat sensor: temperature device class,
    measurement state class, degrees Celsius. Channel letters are not
    separate entities. The value is the newest frame.
    """

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_translation_key = "internal_temperature"

    def __init__(self, coordinator: CXLCoordinator, probe_id: str) -> None:
        """Initialize the internal temperature sensor."""
        super().__init__(coordinator, probe_id, "internal_temperature")

    @property
    def available(self) -> bool:
        """Unavailable when the link is down, the probe is offline, or no frame yet."""
        state = self.probe_state
        return (
            self.coordinator.available
            and state is not None
            and not state.offline
            and state.internal_celsius is not None
        )

    @property
    def native_value(self) -> float | None:
        """Return the internal temperature in Celsius."""
        state = self.probe_state
        if state is None:
            return None
        return state.internal_celsius

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Show which letter produced the reading, without making it a sensor."""
        state = self.probe_state
        attributes = {"probe_id": self._probe_id}
        if state is None:
            return attributes
        if state.channel is not None:
            attributes["channel"] = state.channel
        if state.frame_index is not None:
            attributes["frame_index"] = state.frame_index
        return attributes
