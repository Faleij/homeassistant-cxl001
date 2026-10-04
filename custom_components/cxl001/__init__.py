"""CXL001 / CXL001-C wireless meat probe integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, MODEL, PLATFORMS
from .coordinator import CXLCoordinator

CXLConfigEntry = ConfigEntry[CXLCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: CXLConfigEntry) -> bool:
    """Set up a BBQZ repeater from a config entry."""
    address = entry.data[CONF_ADDRESS]
    coordinator = CXLCoordinator(hass, entry)
    entry.runtime_data = coordinator

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, address)},
        connections={(dr.CONNECTION_BLUETOOTH, address)},
        model=MODEL,
        name=entry.title or f"CXL001 {address}",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CXLConfigEntry) -> bool:
    """Unload a repeater config entry."""
    coordinator = entry.runtime_data
    await coordinator.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
