"""Probe link sensor for the CXL001 repeater."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import CXLCoordinator
from .entity import CXLProbeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add one connectivity sensor per probe id seen on the repeater."""
    coordinator: CXLCoordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def _on_probe(probe_id: str) -> None:
        if probe_id in added:
            return
        added.add(probe_id)
        async_add_entities([CXLProbeLinkSensor(coordinator, probe_id)])

    if coordinator.data is not None:
        for probe_id in coordinator.data.probes:
            _on_probe(probe_id)
    entry.async_on_unload(coordinator.async_add_probe_listener(_on_probe))


class CXLProbeLinkSensor(CXLProbeEntity, BinarySensorEntity):
    """On when the repeater is forwarding temperatures for this probe.

    Off after the captured offline frame (``0000``). This is not a battery
    reading. The protocol has no battery percentage.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "probe"

    def __init__(self, coordinator: CXLCoordinator, probe_id: str) -> None:
        """Initialize the probe link sensor."""
        super().__init__(coordinator, probe_id, "probe")

    @property
    def available(self) -> bool:
        """Available while the repeater link is up and this probe has been seen."""
        return self.coordinator.available and self.probe_state is not None

    @property
    def is_on(self) -> bool | None:
        """True while temperature frames are being forwarded."""
        state = self.probe_state
        if state is None:
            return None
        return not state.offline
