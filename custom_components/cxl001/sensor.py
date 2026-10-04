"""Temperature sensors for a CXL001 / CXL001-C probe."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KNOWN_LETTERS, LETTER_SECOND_INTERNAL, LETTER_TIP
from .coordinator import CXLCoordinator
from .entity import CXLProbeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a temperature sensor per channel the repeater actually sends."""
    coordinator: CXLCoordinator = entry.runtime_data
    added: dict[str, set[str]] = {}

    def _add(probe_id: str, letters: tuple[str, ...] | list[str]) -> None:
        fresh = [letter for letter in letters if letter not in added.setdefault(probe_id, set())]
        if not fresh:
            return
        added[probe_id].update(fresh)
        async_add_entities(
            CXLTemperatureSensor(coordinator, probe_id, letter) for letter in fresh
        )

    @callback
    def _on_probe(probe_id: str) -> None:
        _add(probe_id, KNOWN_LETTERS)

    @callback
    def _on_letter(probe_id: str, letter: str) -> None:
        if probe_id not in added:
            _on_probe(probe_id)
        _add(probe_id, (letter,))

    if coordinator.data is not None:
        for probe_id, state in coordinator.data.probes.items():
            _on_probe(probe_id)
            _on_letter_many = [letter for letter in state.temperatures if letter not in KNOWN_LETTERS]
            if _on_letter_many:
                _add(probe_id, _on_letter_many)

    entry.async_on_unload(coordinator.async_add_probe_listener(_on_probe))
    entry.async_on_unload(coordinator.async_add_letter_listener(_on_letter))


class CXLTemperatureSensor(CXLProbeEntity, SensorEntity):
    """One Celsius channel from the repeater notify stream."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator: CXLCoordinator,
        probe_id: str,
        letter: str,
    ) -> None:
        """Initialize a channel sensor."""
        super().__init__(coordinator, probe_id, f"temp_{letter}")
        self._letter = letter
        if letter == LETTER_TIP:
            self._attr_translation_key = "tip_temperature"
        elif letter == LETTER_SECOND_INTERNAL:
            self._attr_translation_key = "second_internal_temperature"
        else:
            self._attr_translation_key = "channel_temperature"
            self._attr_translation_placeholders = {"letter": letter}

    @property
    def available(self) -> bool:
        """Unavailable when the link is down or this channel has no live value.

        A ``0000`` frame clears channel values, so a docked probe does not keep
        showing the last temperature as if it were still measuring.
        """
        state = self.probe_state
        return (
            self.coordinator.available
            and state is not None
            and not state.offline
            and self._letter in state.temperatures
        )

    @property
    def native_value(self) -> float | None:
        """Return the channel temperature in Celsius."""
        state = self.probe_state
        if state is None:
            return None
        return state.temperatures.get(self._letter)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Expose the channel letter and the unparsed frame index."""
        state = self.probe_state
        attributes = {
            "channel": self._letter,
            "probe_id": self._probe_id,
        }
        if state is not None and state.frame_index is not None:
            attributes["frame_index"] = state.frame_index
        return attributes
