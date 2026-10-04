"""Constants for the CXL001 / CXL001-C repeater integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "cxl001"

# The on-air name is BBQZ. CXL001 and CXL001-C were not separate GATT dialects
# in the local captures; both are represented by this repeater path.
MODEL = "CXL001 / CXL001-C"
REPEATER_MODEL = "CXL001 / CXL001-C repeater"
PROBE_MODEL = "CXL001 / CXL001-C probe"

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Complete local name in the primary advertisement. The temperature service
# UUID is not advertised, so discovery cannot match on it.
LOCAL_NAME = "BBQZ"

# Temperature service. Present after connect, absent from advertising.
SERVICE_UUID = "18424398-7cbc-11e9-8f9e-2a86e4085a59"

# Notify. Every temperature frame in the capture arrived here.
CHAR_TEMPERATURE_NOTIFY = "772ae377-b3d2-ff8e-1042-5481d1e03456"

# Write characteristic on the temperature service. No command bytes were
# captured, so the integration never writes it.
CHAR_TEMPERATURE_WRITE = "0000fff2-0000-1000-8000-00805f9b34fb"

# Vendor service 0xFE11. The read returns a firmware string. The write
# characteristic 0x2C00 was not used.
SERVICE_VENDOR_UUID = "0000fe11-0000-1000-8000-00805f9b34fb"
CHAR_FIRMWARE = "00002c01-0000-1000-8000-00805f9b34fb"

# Letters with a meaning in the local working model.
# X digits matched the probe tip. W is the other internal sensor.
# Do not map either letter to ambient or to battery.
LETTER_TIP = "X"
LETTER_SECOND_INTERNAL = "W"
KNOWN_LETTERS = (LETTER_TIP, LETTER_SECOND_INTERNAL)

# How often to read the firmware characteristic as a link heartbeat.
# Temperature notifications are not periodic, and a docked probe goes silent
# after the 0000 frame, so silence is not a dead link.
LINK_CHECK_INTERVAL = 60.0
LINK_CHECK_TIMEOUT = 10.0
LINK_FAILURES_BEFORE_RECONNECT = 2

RECONNECT_COOLDOWN = 5.0
RECONNECT_COOLDOWN_MAX = 30.0
AVAILABILITY_GRACE = 90.0
ADVERT_SILENCE_RESET = 60.0
MAX_CONNECT_ATTEMPTS = 4
NO_PATH_WARN_AFTER = 8
DISCONNECT_TIMEOUT = 10.0
