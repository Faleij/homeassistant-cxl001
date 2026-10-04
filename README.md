# CXL001 / CXL001-C

Local Home Assistant integration for a CXL001 or CXL001-C wireless meat probe
that reports through a BBQZ Bluetooth repeater.

Author: Faleij.

This repository was cloned from Emkraan/homeassistant-meater and rewritten.
The Meater cloud and Meater GATT protocols are not used. Do not push this
repository until you choose to.

## The one temperature

The frame is ASCII, for example `00:abbcdd02860d:Y29.2&`. The Celsius number
is already in the text. The letter (`W`, `X`, `Y`, `Z`, or another) is not a
separate sensor, not ambient, and not battery.

The internal temperature is that number on the newest frame. That is what
`meater-local (8).html` stores as `state.current.meat` (`applyBbqzReading`
sets it from `decoded.celsius` and the status line says the cook uses the
newest frame). Live readings of Y 29.2 and Z 29.2 are the same internal
temperature reported twice, not two probes.

There is no battery percentage. `0000` means the probe is offline.

## Entities

For each probe id forwarded by the repeater:

- Internal Temperature. Temperature device class, measurement state class,
  degrees Celsius. This is the meat reading, in the same role as the Meater
  integration's tip/internal temperature. The last channel letter is only an
  attribute.
- Probe connectivity. Off after the offline frame `0000`.

The repeater firmware string from GATT `0x2C01`, when it matches `app-â€¦`, is
stored as the repeater device software version.

## Not verified live after this change

Copying the component does not reload Home Assistant. Temperatures will not
follow this model until Home Assistant is restarted again.
