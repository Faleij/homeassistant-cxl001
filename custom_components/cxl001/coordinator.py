"""GATT connection to a CXL001 / CXL001-C BBQZ repeater.

Temperatures are not in the advertisement. The integration connects to the
repeater, subscribes to the notify characteristic, and parses ASCII frames.
It does not speak the Meater protocol and it does not write commands.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ADVERT_SILENCE_RESET,
    AVAILABILITY_GRACE,
    CHAR_FIRMWARE,
    CHAR_TEMPERATURE_NOTIFY,
    DISCONNECT_TIMEOUT,
    DOMAIN,
    LINK_CHECK_INTERVAL,
    LINK_CHECK_TIMEOUT,
    LINK_FAILURES_BEFORE_RECONNECT,
    MAX_CONNECT_ATTEMPTS,
    NO_PATH_WARN_AFTER,
    RECONNECT_COOLDOWN,
    RECONNECT_COOLDOWN_MAX,
)
from .parser import (
    IgnoredSample,
    ProbeOffline,
    TemperatureSample,
    parse_firmware,
    parse_temperature_notify,
)

_LOGGER = logging.getLogger(__name__)

ProbeListener = Callable[[str], None]


@dataclass
class ProbeState:
    """Latest forwarded state for one probe id.

    internal_celsius is the newest temperature frame, any channel letter.
    The letter is kept only as an attribute. It is not a separate sensor.
    """

    probe_id: str
    frame_index: str | None = None
    internal_celsius: float | None = None
    channel: str | None = None
    offline: bool = False


@dataclass
class RepeaterData:
    """Latest data from one BBQZ repeater connection."""

    firmware: str | None = None
    probes: dict[str, ProbeState] = field(default_factory=dict)


class CXLCoordinator(DataUpdateCoordinator[RepeaterData]):
    """Keep a notify subscription to one BBQZ repeater."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator for a configured repeater address."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
        )
        self.address: str = entry.data["address"]
        self._entry = entry
        self._client: BleakClientWithServiceCache | None = None
        self._connected = False
        self._connecting = False
        self._closing = False
        self._expected_disconnect = False
        self._connect_task: asyncio.Task[None] | None = None
        self._cancel_reconnect: CALLBACK_TYPE | None = None
        self._cancel_bluetooth: CALLBACK_TYPE | None = None
        self._cancel_link_check: CALLBACK_TYPE | None = None
        self._cancel_grace: CALLBACK_TYPE | None = None
        self._grace_active = False
        self._reconnect_backoff = RECONNECT_COOLDOWN
        self._no_path_count = 0
        self._last_advert = 0.0
        self._link_failures = 0
        self._checking_link = False
        self._probe_listeners: list[ProbeListener] = []
        self._announced_probes: set[str] = set()
        self._logged_ignored: set[str] = set()
        self._snapshot = RepeaterData()

    @property
    def available(self) -> bool:
        """True while connected, and briefly after an unexpected drop."""
        return self._connected or self._grace_active

    @callback
    def async_add_probe_listener(self, listener: ProbeListener) -> CALLBACK_TYPE:
        """Register a callback for the first time a probe id is seen."""
        self._probe_listeners.append(listener)

        def _remove() -> None:
            if listener in self._probe_listeners:
                self._probe_listeners.remove(listener)

        return _remove

    @callback
    def async_start(self) -> None:
        """Listen for the repeater and connect."""
        self._closing = False
        self._cancel_bluetooth = bluetooth.async_register_callback(
            self.hass,
            self._async_on_advertisement,
            BluetoothCallbackMatcher(address=self.address, connectable=False),
            BluetoothScanningMode.ACTIVE,
        )
        self._schedule_connect()

    async def async_stop(self) -> None:
        """Stop reconnecting and disconnect."""
        self._closing = True
        self._expected_disconnect = True
        if self._cancel_bluetooth is not None:
            self._cancel_bluetooth()
            self._cancel_bluetooth = None
        if self._cancel_reconnect is not None:
            self._cancel_reconnect()
            self._cancel_reconnect = None
        self._stop_link_check()
        self._clear_grace()
        if self._connect_task is not None:
            self._connect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._connect_task
            self._connect_task = None
        await self._async_disconnect()

    @callback
    def _async_on_advertisement(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """Reconnect when the repeater is heard again."""
        if self._closing or self._connected:
            return
        now = self.hass.loop.time()
        if now - self._last_advert > ADVERT_SILENCE_RESET:
            self._reconnect_backoff = RECONNECT_COOLDOWN
        self._last_advert = now
        self._schedule_connect()

    @callback
    def _schedule_connect(self, delay: float = 0.0) -> None:
        """Start a connection attempt, or queue one after a cooldown."""
        if self._closing or self._connected:
            return
        if self._cancel_reconnect is not None:
            return
        if delay > 0:
            self._cancel_reconnect = async_call_later(
                self.hass, delay, self._async_reconnect_fire
            )
            return
        if self._connecting:
            return
        if self._connect_task is not None and not self._connect_task.done():
            return
        self._connect_task = self.hass.async_create_background_task(
            self._async_connect(),
            name=f"{DOMAIN}_connect:{self.address}",
        )

    @callback
    def _async_reconnect_fire(self, _now: object) -> None:
        """Run a cooldown-delayed connect."""
        self._cancel_reconnect = None
        self._schedule_connect()

    def _schedule_reconnect(self) -> None:
        """Back off and try again."""
        if self._closing or self._connected:
            return
        delay = self._reconnect_backoff
        self._reconnect_backoff = min(self._reconnect_backoff * 2, RECONNECT_COOLDOWN_MAX)
        self._schedule_connect(delay)

    async def _async_connect(self) -> None:
        """Connect, subscribe to temperature notifications, and read firmware."""
        if self._connected or self._closing:
            return
        self._connecting = True
        retry = False
        try:
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                self._no_path_count += 1
                if self._no_path_count == NO_PATH_WARN_AFTER:
                    _LOGGER.warning(
                        "CXL001 repeater %s has no connectable Bluetooth path after "
                        "repeated attempts. The repeater must be advertising the name "
                        "BBQZ, and another phone app may already be holding its only "
                        "connection",
                        self.address,
                    )
                else:
                    _LOGGER.debug(
                        "CXL001 repeater %s has no connectable path yet",
                        self.address,
                    )
                retry = True
                return
            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    f"{DOMAIN}-{self.address}",
                    disconnected_callback=self._on_disconnect,
                    max_attempts=MAX_CONNECT_ATTEMPTS,
                    ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                        self.hass, self.address, connectable=True
                    ),
                )
            except (BleakError, asyncio.TimeoutError) as err:
                _LOGGER.debug(
                    "CXL001 repeater %s connection failed: %s", self.address, err
                )
                retry = True
                return
            try:
                await client.start_notify(CHAR_TEMPERATURE_NOTIFY, self._on_notify)
            except (BleakError, asyncio.TimeoutError) as err:
                _LOGGER.debug(
                    "CXL001 repeater %s failed to subscribe: %s", self.address, err
                )
                self._expected_disconnect = True
                with contextlib.suppress(BleakError, asyncio.TimeoutError, EOFError):
                    await client.disconnect()
                retry = True
                return
            self._client = client
            self._connected = True
            self._expected_disconnect = False
            self._reconnect_backoff = RECONNECT_COOLDOWN
            self._no_path_count = 0
            self._link_failures = 0
            self._clear_grace()
            _LOGGER.info("Connected to CXL001 repeater %s", self.address)
            await self._async_read_firmware(client)
            self._start_link_check()
            self.async_update_listeners()
        finally:
            self._connecting = False
            if retry and not self._closing and not self._connected:
                self._schedule_reconnect()

    def _on_disconnect(self, client: BleakClientWithServiceCache) -> None:
        """Hop a Bleak disconnect callback onto the event loop."""
        self.hass.loop.call_soon_threadsafe(self._async_on_disconnect, client)

    def _on_notify(self, *args: object) -> None:
        """Accept either bleak's data-only callback or the older (char, data) form."""
        if not args:
            return
        data = args[-1]
        if not isinstance(data, (bytes, bytearray, memoryview)):
            _LOGGER.debug("CXL001 %s notify had no bytes: %s", self.address, args)
            return
        self.hass.loop.call_soon_threadsafe(self._handle_notify, bytes(data))

    @callback
    def _async_on_disconnect(self, client: BleakClientWithServiceCache) -> None:
        """Handle the repeater dropping the link."""
        if client is not self._client:
            return
        self._connected = False
        self._client = None
        self._stop_link_check()
        _LOGGER.debug(
            "CXL001 repeater %s disconnected (expected=%s)",
            self.address,
            self._expected_disconnect,
        )
        if not self._expected_disconnect and not self._closing:
            self._start_grace()
            self._schedule_reconnect()
        self.async_update_listeners()

    async def _async_disconnect(self) -> None:
        """Drop the current client."""
        self._stop_link_check()
        client = self._client
        self._client = None
        self._connected = False
        if client is not None and client.is_connected:
            with contextlib.suppress(BleakError, asyncio.TimeoutError, EOFError):
                await asyncio.wait_for(client.disconnect(), timeout=DISCONNECT_TIMEOUT)

    @callback
    def _start_link_check(self) -> None:
        """Periodically read firmware to notice a half-open link."""
        self._stop_link_check()
        self._cancel_link_check = async_track_time_interval(
            self.hass,
            self._async_link_check,
            timedelta(seconds=LINK_CHECK_INTERVAL),
            name=f"{DOMAIN}_link:{self.address}",
        )

    @callback
    def _stop_link_check(self) -> None:
        """Cancel the firmware heartbeat."""
        if self._cancel_link_check is not None:
            self._cancel_link_check()
            self._cancel_link_check = None

    async def _async_link_check(self, _now: object) -> None:
        """Read the firmware characteristic. Failure means the link is dead."""
        client = self._client
        if (
            not self._connected
            or client is None
            or self._closing
            or self._checking_link
        ):
            return
        self._checking_link = True
        try:
            ok = await self._async_read_firmware(client)
            if ok:
                self._link_failures = 0
                return
            self._link_failures += 1
            if self._link_failures >= LINK_FAILURES_BEFORE_RECONNECT:
                await self._async_recover()
        finally:
            self._checking_link = False

    async def _async_read_firmware(self, client: BleakClientWithServiceCache) -> bool:
        """Read ``0x2C01``. Return False when the read itself fails."""
        try:
            raw = await asyncio.wait_for(
                client.read_gatt_char(CHAR_FIRMWARE),
                timeout=LINK_CHECK_TIMEOUT,
            )
        except (BleakError, asyncio.TimeoutError, EOFError) as err:
            _LOGGER.debug(
                "CXL001 repeater %s firmware read failed: %s", self.address, err
            )
            return False
        firmware = parse_firmware(bytes(raw))
        if firmware and firmware != self._snapshot.firmware:
            self._snapshot.firmware = firmware
            self._async_update_device_firmware(firmware)
            self.async_set_updated_data(self._snapshot)
        return True

    @callback
    def _async_update_device_firmware(self, firmware: str) -> None:
        """Store the repeater firmware string on the device registry entry."""
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(identifiers={(DOMAIN, self.address)})
        if device is not None:
            registry.async_update_device(device.id, sw_version=firmware)

    async def _async_recover(self) -> None:
        """Reconnect after the firmware read failed twice."""
        if not self._connected or self._closing:
            return
        _LOGGER.info(
            "CXL001 repeater %s link looks dead; reconnecting",
            self.address,
        )
        self._expected_disconnect = True
        self._start_grace()
        await self._async_disconnect()
        self.async_update_listeners()
        self._schedule_reconnect()

    @callback
    def _start_grace(self) -> None:
        """Keep the last reading across a short reconnect."""
        if self._cancel_grace is not None or self.data is None:
            return
        self._grace_active = True
        self._cancel_grace = async_call_later(
            self.hass, AVAILABILITY_GRACE, self._async_grace_expired
        )

    @callback
    def _async_grace_expired(self, _now: object) -> None:
        """Stop serving stale data."""
        self._cancel_grace = None
        self._grace_active = False
        self.async_update_listeners()

    @callback
    def _clear_grace(self) -> None:
        """Cancel the availability grace window."""
        if self._cancel_grace is not None:
            self._cancel_grace()
            self._cancel_grace = None
        self._grace_active = False

    def _handle_notify(self, payload: bytes) -> None:
        """Parse one notification on the event loop."""
        try:
            parsed = parse_temperature_notify(payload)
        except Exception:
            _LOGGER.exception("CXL001 %s notify parse failed", self.address)
            return
        if parsed is None:
            _LOGGER.debug(
                "CXL001 %s ignored notify %s", self.address, payload.hex()
            )
            return
        if isinstance(parsed, IgnoredSample):
            if parsed.probe_id not in self._logged_ignored:
                self._logged_ignored.add(parsed.probe_id)
                _LOGGER.warning(
                    "CXL001 probe %s sent token 999 on channel %s; not stored as 0 C",
                    parsed.probe_id,
                    parsed.letter,
                )
            return
        state = self._snapshot.probes.get(parsed.probe_id)
        new_probe = state is None
        if state is None:
            state = ProbeState(probe_id=parsed.probe_id)
            self._snapshot.probes[parsed.probe_id] = state
        state.frame_index = parsed.frame_index
        if isinstance(parsed, ProbeOffline):
            state.offline = True
            state.internal_celsius = None
            state.channel = None
            _LOGGER.info("CXL001 probe %s reported offline", parsed.probe_id)
        elif isinstance(parsed, TemperatureSample):
            # Newest frame wins, whatever the letter is. See parser.internal_celsius.
            state.offline = False
            state.internal_celsius = parsed.celsius
            state.channel = parsed.letter
        self.async_set_updated_data(self._snapshot)
        if new_probe and parsed.probe_id not in self._announced_probes:
            self._announced_probes.add(parsed.probe_id)
            for listener in list(self._probe_listeners):
                listener(parsed.probe_id)

    async def _async_update_data(self) -> RepeaterData:
        """Not polled. Notifications push updates."""
        if self.data is not None:
            return self.data
        return self._snapshot
