# wakemypc

Companion CLI for [wakemypc.com](https://wakemypc.com). Runs on your computer, talks to a Pi Pico W (or W 2) over USB, and your wakemypc.com account over HTTP.

## Install

Direct from GitHub (recommended for now -- no PyPI release yet):

```bash
pip install git+https://github.com/wakemypc/wakemypc-cli.git
```

Verify:

```bash
wakemypc --help
```

On Linux you may need to add yourself to the `dialout` group so you can talk to the Pico's serial port without `sudo`:

```bash
sudo usermod -a -G dialout $USER
# log out and back in
```

## What it does

```
wakemypc detect           # list connected Picos (flashed and BOOTSEL-mode)
wakemypc flash --uf2 …    # write MicroPython firmware to a BOOTSEL Pico
wakemypc upload …         # copy wakemypc-firmware .py files onto the Pico
wakemypc provision …      # write WiFi creds + server URL to secrets.json
wakemypc register …       # register with the server, get a device token
wakemypc restart          # soft-reboot the Pico (or reboot into BOOTSEL)
wakemypc identify         # blink the Pico's LED to find it physically
wakemypc status           # read WiFi state + secrets summary over USB
```

`wakemypc --help` and `wakemypc <subcommand> --help` have the full reference. The most common flow for a brand new Pico is:

```bash
# 1) Plug Pico in BOOTSEL mode (hold BOOTSEL while connecting USB).
wakemypc detect
wakemypc flash --uf2 RPI_PICO2_W-…uf2

# 2) Plug the now-flashed Pico in normally.
wakemypc upload --firmware-dir ./wakemypc-firmware/src/

# 3) Configure WiFi + server.
wakemypc provision --server-url https://wakemypc.com --add-new-wifi --wifi-ssid HomeWiFi --wifi-pass mypassword

# 4) Register on wakemypc.com.
wakemypc register --api-url https://wakemypc.com --username you@example.com
# (prompts for password; saves the resulting device token to the Pico)
```

## Token rotation

Three modes:

```bash
wakemypc register --api-url https://wakemypc.com --username … --password …            # fresh
wakemypc register --api-url https://wakemypc.com --username … --password … --rotate   # rotate existing
wakemypc register --token <T>                                                          # offline, no server call
```

`--rotate` calls the server's rotate-token endpoint and writes the new token to the Pico in one step. `--token <T>` skips the server -- handy when you've already rotated through the dashboard and just need to push the new token over USB.

## What this CLI does NOT do

- It does not need root / sudo (apart from the one-time `dialout` group add on Linux).
- It does not phone home. The only network calls go to the `--api-url` you pass to `register`.
- It does not store your password. Login uses the JWT the server returns; the password is forwarded once and then forgotten.

## License

**Source-available, non-commercial.** [PolyForm Noncommercial 1.0.0](LICENSE).

You can run it, audit it, modify it, and share patches. You can't sell it or run a paid service on top of it. Patches welcome.
