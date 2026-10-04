"""Config flow for the CXL001 / CXL001-C repeater."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN, LOCAL_NAME, MODEL


def _is_repeater(discovery_info: BluetoothServiceInfoBleak) -> bool:
    """Return True for the BBQZ repeater name.

    The temperature service UUID is not in the advertisement. Matching only the
    name avoids the other BBQ* products, which use a different binary protocol.
    A name of exactly BBQ (the app's direct-probe mode) is not this device.
    """
    return (discovery_info.name or "").casefold() == LOCAL_NAME.casefold()


def _title(discovery_info: BluetoothServiceInfoBleak) -> str:
    """Human title for a discovered repeater."""
    name = discovery_info.name
    if name and name.casefold().startswith(LOCAL_NAME.casefold()):
        return f"{name} {discovery_info.address}"
    return f"CXL001 {discovery_info.address}"


class CXLConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle discovery and manual setup of a BBQZ repeater."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a repeater discovered by the local-name matcher."""
        if not _is_repeater(discovery_info):
            return self.async_abort(reason="not_repeater")
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": _title(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the discovered repeater."""
        assert self._discovery_info is not None
        title = _title(self._discovery_info)
        if user_input is not None:
            return self.async_create_entry(
                title=title,
                data={CONF_ADDRESS: self._discovery_info.address},
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": title,
                "address": self._discovery_info.address,
                "model": MODEL,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick a BBQZ repeater from the current scan."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._discovered.get(address, f"CXL001 {address}"),
                data={CONF_ADDRESS: address},
            )

        await bluetooth.async_request_active_scan(self.hass)
        current = self._async_current_ids(include_ignore=False)
        discovered: dict[str, str] = {}
        for discovery_info in async_discovered_service_info(self.hass, connectable=True):
            if discovery_info.address in current or not _is_repeater(discovery_info):
                continue
            discovered[discovery_info.address] = _title(discovery_info)
        self._discovered = discovered
        if not discovered:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(discovered)}
            ),
        )
