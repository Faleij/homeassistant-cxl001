"""Base entities for the CXL001 repeater integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, PROBE_MODEL
from .coordinator import CXLCoordinator, ProbeState


class CXLProbeEntity(CoordinatorEntity[CXLCoordinator]):
    """An entity for one probe id forwarded by the BBQZ repeater."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CXLCoordinator,
        probe_id: str,
        unique_suffix: str,
    ) -> None:
        """Tie the entity to the probe device behind this repeater."""
        super().__init__(coordinator)
        self._probe_id = probe_id
        self._attr_unique_id = f"{coordinator.address}_{probe_id}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.address}:{probe_id}")},
            name=f"CXL001 {probe_id}",
            model=PROBE_MODEL,
            serial_number=probe_id,
            via_device=(DOMAIN, coordinator.address),
        )

    @property
    def probe_state(self) -> ProbeState | None:
        """Current state for this probe, if a frame has been seen."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.probes.get(self._probe_id)
