# paperbutler · Local-network control bridge for smart devices

A direct-on-LAN control bridge built on `python-miio`. No vendor cloud, no general-purpose home-automation platform: miIO commands go straight to the devices on your own network. The bridge also exposes a compact HTTP API for clients that cannot speak UDP (for example Lua sandboxes).

> **paperbutler** is the server-side companion of an ESP32 application of the same name. The device-side app drives the LAN through this bridge's HTTP API; the service is equally usable standalone, with a built-in web console. The name: *paper* + *butler*.

> **Chinese version:** see [README.md](README.md).

> **Licence: GPL-3.0-only** (strong copyleft). Full text in [LICENSE](LICENSE); third-party notices in [NOTICE](NOTICE).
>
> **Disclaimer:** this is a voluntary, community-driven effort. It is not affiliated with, endorsed by, or sponsored by any of the companies whose devices it can talk to. Product, model and protocol names are used only in a descriptive, interoperability sense (nominative fair use).

## Repository contents

```
.
├── app.py                      # Flask service: web console + HTTP bridge
├── templates/index.html        # front-end page
├── requirements.txt            # runtime dependencies (two packages)
├── devices.example.json        # device configuration template (placeholders only, safe to commit)
├── API.md                      # HTTP bridge contract (for device-side clients)
├── LICENSE                     # full GNU GPLv3 text
├── NOTICE                      # third-party components, licences and copyrights
├── README.md                   # Chinese README
├── README.en.md                # this file
├── setup.sh                    # one-shot deployment helper
└── .gitignore                  # excludes local credentials, virtualenvs and downloaded helpers
```

Deliberately excluded: `.venv/`, `token-extractor/`, `devices.json`, `tokens.json`, `__pycache__/`. Rationale and retrieval instructions are in *Non-mandatory components* below.

## Quick start

### Option A: setup script (recommended)

```bash
./setup.sh                          # runtime dependencies only
./setup.sh --with-token-extractor   # additionally fetch the token-export helper
```

The script creates `.venv`, installs `requirements.txt`, generates `devices.json` from the template and, optionally, clones the token-export helper. Every generated artefact is covered by `.gitignore`, so the working tree stays clean. The script is non-interactive and runs unattended in CI or on a fresh machine.

### Option B: manual

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp devices.example.json devices.json
```

## Obtaining a device token (one-time setup)

A token is needed only when you configure the bridge for the first time, or when a device regenerates it. The token-export helper is a separate MIT-licensed project and is **not bundled** with this repository. Two ways to get it:

```bash
# Option A: via the setup script
./setup.sh --with-token-extractor

# Option B: manually
git clone --depth 1 https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor.git token-extractor
python3 -m venv token-extractor/.venv
token-extractor/.venv/bin/pip install -r token-extractor/requirements.txt
cd token-extractor && .venv/bin/python token_extractor.py -s cn -o tokens.json
```

Use the helper only with devices that you own. Copy the resulting IP / token / model values into `devices.json`. Only this initial token retrieval involves the vendor account; **all control traffic afterwards stays on the local network**. Tokens rotate after a device is reset or re-provisioned, and sometimes after a firmware update. Re-export them when that happens.

## Configuring devices.json

`devices.json` is created from the template. **Every placeholder must be replaced:**

| Placeholder | Replace with | Notes |
|---|---|---|
| `<REPLACE_WITH_32_HEX_TOKEN>` | 32-character hexadecimal string | Device token, obtained from your own account |
| `<DEVICE_LAN_IP>` | The device's LAN IPv4 address | Prefer a static IP or a DHCP reservation |
| `<EXAMPLE_LAN_IP>` | Same as above | For the remaining example devices in the template |
| `<BRIDGE_HOST_IP>` | LAN IPv4 address of the host running this bridge | Used by device-side clients |

> The token must be a valid 32-character hexadecimal string. If you leave the placeholder untouched, `GET /devices` still returns the list, but the status and control endpoints answer with a clear "token missing or invalid length" message.
>
> `devices.json` holds real credentials. It is excluded by `.gitignore`: **never commit it and never share it**.

`type` accepts `yeelight`, `chuangmi_plug` / `plug`, or `miot`. Modern MIoT devices declare their `siid` / `piid` pairs under `mapping` (look them up for your model on miot-spec.org); every property you declare becomes a control in the web console. Action-style devices such as rice cookers are described with `actions` / `options` / `value_labels`; see the template.

## Running

```bash
.venv/bin/python app.py
```

- Local web console: <http://127.0.0.1:9090>
- Device-side URL: `http://<BRIDGE_HOST_IP>:9090`. Replace with the host's real LAN address. **Use `http://`**; clients reject the self-signed certificate under HTTPS.

The service binds to `0.0.0.0:9090`. The bridge and the devices must share an IPv4 subnet, with AP isolation and guest-network isolation disabled.

## Non-mandatory components

| Component | Purpose | Why it is not bundled | How to get it |
|---|---|---|---|
| `.venv/` | Python virtual environment | Local build artefact, platform-bound, bulky | `setup.sh` or `python3 -m venv .venv` |
| `token-extractor/` | One-off token export | Third-party MIT project; not required at runtime; bundling it adds distribution obligations | `setup.sh --with-token-extractor` or the manual commands above |
| `devices.json` | Your real configuration | Contains tokens / LAN IPs / MAC addresses (credentials) | Copy `devices.example.json` and fill it in |
| `tokens.json`, `__pycache__/`, `*.pyc` | Export output / bytecode cache | Credentials or build artefacts, unrelated to the source | Generated automatically; git-ignored |

Runtime dependencies are only the two packages listed in `requirements.txt`; the token-export helper is a configuration-time convenience. If you redistribute `token-extractor/` alongside this repository, keep its MIT licence and copyright notice (see `NOTICE`).

## HTTP bridge API

```
GET  /devices                  device list (capabilities / actions / options / value_labels)
GET  /devices/{id}/status      current state
POST /devices/{id}/set         power / property writes (validated against capabilities)
POST /devices/{id}/action      action-style devices (start / cancel cooking, …)
```

Field-level details, capability validation, mode values and Lua-sandbox constraints live in [API.md](API.md).

## Caveats

- Keep the bridge and the devices on the same subnet; give devices a static IP or a DHCP reservation, since a changed address breaks the link.
- A firmware update may rotate a device token; re-export it and update `devices.json`.
- Zigbee and Bluetooth-Mesh sub-devices carry no individual token, so this approach does not apply to them; only gateways expose one.
- The bundled examples cover one light and one rice cooker; other device families have to be wired up by you.

## Licence and compliance

Released under the **GNU General Public License, version 3 only (GPL-3.0-only)**; the full text is in [LICENSE](LICENSE).

**Why GPLv3:** the core library `python-miio` is published under `GPL-3.0-only`. This project links it at runtime, so the combination forms a single covered work and redistribution must happen under GPLv3 as a whole. No part of `python-miio` is modified here; it is pulled in through `requirements.txt` and imported as `miio`.

- You may run, modify and redistribute the project, including commercially. On redistribution you must retain the copyright and licence notices, ship the full GPLv3 text, provide the complete corresponding source under GPL-3.0-only, and impose no further restrictions.
- The software is provided **without any warranty** (LICENSE §15–§16).
- Third-party components and copyrights are enumerated in [NOTICE](NOTICE). The MIT / BSD / Apache-2.0 / LGPL / MPL components in the dependency tree are compatible with GPLv3.
- **Trademarks:** "Mijia", "Xiaomi" and "MIoT" are trademarks of their respective owner. They appear here only descriptively, for interoperability (nominative fair use), and imply no endorsement, sponsorship or affiliation.

> Running the software on your own machines, without handing out copies, does not trigger GPLv3 distribution obligations. This repository is still released under those terms.

## Third-party attribution summary

| Component | Licence | Copyright |
|---|---|---|
| python-miio 0.5.12 | GPL-3.0-only | Teemu R. and python-miio contributors |
| Flask 3.1.3 | BSD-3-Clause | Copyright (c) 2010 Pallets |
| Xiaomi-cloud-tokens-extractor (not bundled) | MIT | Copyright (c) 2020 Piotr Machowski |

The authoritative, complete list (including transitive dependencies) is [NOTICE](NOTICE).
