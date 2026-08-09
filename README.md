# Solakon Cloud for Home Assistant

Prototype Home Assistant integration for Solakon cloud-connected microinverters.

It was developed and tested with a **Solakon onLite** system using the
**Marstek MST-MI0800W / MI800** inverter.

> [!WARNING]
> This project uses the undocumented API used by Solakon's own app. It is not an
> official Solakon integration and may stop working when Solakon changes its API.
> Controls can change inverter behavior; use them carefully.

## Features

- Passwordless Solakon login using the normal email OTP flow
- Renewable session stored by Home Assistant; an OTP is not needed after every restart
- Five-minute cloud polling, matching Solakon's data refresh interval
- Automatic inverter discovery
- Current production
- Energy produced today and lifetime energy
- PV1/PV2 voltage, current and power
- AC voltage, current, power and frequency when supplied by the device
- Inverter temperature when supplied by the device
- Wi-Fi signal, connectivity and last-update diagnostics
- B2500 operating-mode switch when the device reports support
- Maximum-output control only when Solakon returns its current value

Entities for values that the API returns as `null` are intentionally not created.
For the tested MI800, temperature and AC current were unavailable. Solakon also
returned `404 no-data` for maximum power, so that control was withheld.

## Installation with HACS

1. Open HACS in Home Assistant.
2. Open **Integrations** and select the three-dot menu.
3. Select **Custom repositories**.
4. Add `https://github.com/LinkeTh/ha_solakon` as an **Integration** repository.
5. Install **Solakon Cloud (Prototype)**.
6. Restart Home Assistant.

## Manual installation

Copy `custom_components/solakon_cloud` into Home Assistant's
`/config/custom_components/` directory and restart Home Assistant.

## Configuration

1. Open **Settings → Devices & services → Add integration**.
2. Search for **Solakon Cloud (Prototype)**.
3. Enter the email address used by the Solakon app.
4. Enter the six-digit confirmation code received by email.

The integration stores the resulting access and refresh tokens in Home
Assistant's config-entry storage. It does not request or store a password.

## Known limitations

- Cloud-only; this is not a local integration.
- Solakon normally refreshes inverter data every five minutes.
- The private API has no compatibility guarantee.
- Grid-connection blocking is not exposed.
- Maximum-output control is hidden when Solakon returns no current value.
- Adding a newly registered inverter may require reloading the integration.

## Removal

Remove the integration under **Settings → Devices & services**. To remove its
files as well, delete `/config/custom_components/solakon_cloud` and restart Home
Assistant.
