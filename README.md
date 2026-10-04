# CXL001 / CXL001-C

Local Home Assistant integration for a CXL001 or CXL001-C wireless meat probe
that reports through a BBQZ Bluetooth repeater.

Author: Faleij.

This repository was cloned from Emkraan/homeassistant-meater and rewritten.
The Meater cloud and Meater GATT protocols are not used. Do not push this
repository until a probe has been seen by a restarted Home Assistant.

## What it connects to

The phone-facing radio in the local captures is the repeater, advertised as
`BBQZ`. The probe id inside the temperature frame does not advertise and is
not a connection target. Discovery matches the local name `BBQZ` only. The
temperature service UUID is not in the advertisement.

## Entities

For each probe id forwarded by the repeater:

- Tip temperature, channel `X`, Celsius. The captured `X` digits matched a tip reading.
- Second internal temperature, channel `W`, Celsius. This is the other internal sensor. It is not ambient and it is not battery.
- Channel `Y` or `Z` temperature, only if that letter is actually received. Those letters were seen on the air as temperatures. Their physical position is not known.
- Probe connectivity. Off after the offline frame `0000`.

There is no battery entity. No battery percentage was on the air. The repeater
firmware string from GATT `0x2C01`, when it matches `app-â€¦`, is stored as the
repeater device software version.

## Not verified live

The component is installed as files only. Home Assistant has not been restarted,
and this repository was not checked against a probe that was in range at install
time. It cannot be reporting temperatures until both of those happen.
