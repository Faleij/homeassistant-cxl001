"""Parse CXL001 / BBQZ repeater notifications.

On-air temperature frames are ASCII, not a binary struct and not a scaled
integer. Captured shape (local protocol notes, 2026-10-03):

    00:abbcdd02860d:X25.9&

The number is already Celsius. The prefix letter is a channel on that probe,
not a battery percentage and not an ambient temperature.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TemperatureSample:
    """One temperature channel from a live frame."""

    frame_index: str
    probe_id: str
    letter: str
    celsius: float


@dataclass(frozen=True, slots=True)
class ProbeOffline:
    """The repeater reported the probe as disconnected.

    Captured frame: ``00:abbcdd02860d:0000&``. The app also treats an empty
    third field, or any third field containing ``0000``, as disconnect.
    """

    frame_index: str
    probe_id: str


@dataclass(frozen=True, slots=True)
class IgnoredSample:
    """A frame whose numeric token is ``999``.

    Aicooking rewrites that token to ``0.00`` before display. It was not seen
    on this hardware, so it must not become a real 0 C reading.
    """

    frame_index: str
    probe_id: str
    letter: str


ParseResult = TemperatureSample | ProbeOffline | IgnoredSample


def parse_temperature_notify(payload: bytes) -> ParseResult | None:
    """Parse one temperature notification. Return None if it is not a frame."""
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError:
        return None
    text = text.strip("\r\n")
    if not text.endswith("&") or text.count(":") < 2:
        return None
    index, probe_id, field = text[:-1].split(":", 2)
    probe_id = probe_id.strip().lower()
    field = field.strip()
    if not index or not _is_probe_id(probe_id):
        return None
    if field == "" or "0000" in field:
        return ProbeOffline(frame_index=index, probe_id=probe_id)
    letter = field[0].upper()
    if not ("A" <= letter <= "Z"):
        return None
    number = field[1:]
    if number == "999":
        return IgnoredSample(frame_index=index, probe_id=probe_id, letter=letter)
    try:
        celsius = float(number)
    except ValueError:
        return None
    if celsius != celsius or celsius in (float("inf"), float("-inf")):
        return None
    return TemperatureSample(
        frame_index=index,
        probe_id=probe_id,
        letter=letter,
        celsius=celsius,
    )


def parse_firmware(payload: bytes) -> str | None:
    """Parse the vendor ``0x2C01`` read.

    Captured bytes are ``03 80`` followed by ASCII ``app-1.0.7-20240326.1100``.
    The two prefix bytes are not a version. Anything else is left unknown.
    """
    if len(payload) < 6 or payload[0] != 0x03 or payload[1] != 0x80:
        return None
    try:
        text = payload[2:].decode("ascii")
    except UnicodeDecodeError:
        return None
    if not text.startswith("app-"):
        return None
    if any(ord(char) < 32 or ord(char) > 126 for char in text):
        return None
    return text


def internal_celsius(frames: list[ParseResult]) -> float | None:
    """Return the one internal temperature.

    The HTML cook path stores ``state.current.meat`` from the newest frame and
    says the cook uses that frame. The channel letter is not a separate sensor.
    An offline frame clears the reading. A ``999`` token does not become 0 C.
    """
    value: float | None = None
    for frame in frames:
        if isinstance(frame, ProbeOffline):
            value = None
        elif isinstance(frame, TemperatureSample):
            value = frame.celsius
    return value


def _is_probe_id(value: str) -> bool:
    """Probe ids on the air are 12 lowercase hex digits."""
    return len(value) == 12 and all(char in "0123456789abcdef" for char in value)
