# WakeMyPC

Companion CLI for [wakemypc.com](https://wakemypc.com). 

Runs on your computer, talks to a Pi Pico W (or W 2) over USB, and your wakemypc.com account over HTTPS.

## Install

Create a virtual environment.
```bash
python -m venv .venv
```

Use pip:

```bash
pip install wakemypc
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

```bash
wakemypc detect           # list connected Picos (flashed and BOOTSEL-mode)
wakemypc flash --uf2 …    # write MicroPython firmware to a BOOTSEL Pico
wakemypc upload …         # copy wakemypc-firmware .py files onto the Pico
wakemypc provision …      # write WiFi creds + server URL to secrets.json
wakemypc register …       # register with the server, get a device token
wakemypc restart          # soft-reboot the Pico (or reboot into BOOTSEL)
wakemypc identify         # blink the Pico's LED to find it physically usefull when multiple pico(s) connected
wakemypc status           # read WiFi state + secrets summary over USB
wakemypc logs             # Read logs from Pico over USB serial connection 
```

`wakemypc --help` and `wakemypc <subcommand> --help` have the full reference. 

## First Setup

The most common flow for a brand new Pico is:

```bash
# 1) Plug Pico in BOOTSEL mode (hold BOOTSEL while connecting USB).
wakemypc detect
wakemypc flash --uf2 RPI_PICO2_W-…uf2

# 2) Plug the now-flashed Pico to upload latest firmware from GitHub.
wakemypc upload --github

# 3) Configure WiFi + server.
wakemypc provision --add-new-wifi --wifi-ssid HomeWiFi --wifi-pass mypassword

# 4) Register on wakemypc.com.
wakemypc register --username username --password mypassword 
# or 
# Use Token based registeration When using Goggle SignIn (Future versions will support login through browsers)
wakemypc register --token <Token> # Check
```

## Auth Token registeration (Manual)

Register the token offline when
-  You obtained the auth token by manually registering Pico device on dashboard


```bash
wakemypc register --token <Token>
```

This doesn't require any username or password. The Pico will automatically communicate with the server if the Pico is registered on Transmitters on the dashboard.

## Token rotation

In the event that you'd like to rotate the auth token used while authenticating with the server.

Two modes:

```bash
wakemypc register --username … --password … --rotate   # rotate existing
wakemypc register --token <T>                                                          # offline, no server call
```

`--rotate` calls the server's rotate-token endpoint and writes the new token to the Pico in one step. 

`--token <T>` skips the server -- handy when you've already rotated through the dashboard and just need to push the new token over USB.

## What this CLI does NOT do

- It does not need root / sudo (apart from the one-time `dialout` group add on Linux).
- It does not support Pico Token registeration through  dashboard yet. The only network calls go to the api url with `username` and `password`that you pass to `register`.
- It does not store your password. Login uses the JWT the api server returns; the password is forwarded once and then forgotten.

## License

**Source-available, non-commercial.** [PolyForm Noncommercial 1.0.0](LICENSE).

You can run it, audit it, modify it, and share patches. You can't sell it or run a paid service on top of it. Patches welcome.
