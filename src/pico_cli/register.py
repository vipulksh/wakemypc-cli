"""
register.py -- Register a Pico device on the Django server
============================================================

THE REGISTRATION FLOW
---------------------
Before a Pico can send data to your server, it needs to be "registered" -- the
server needs to know about it and give it a unique authentication token.

Here is the full flow:

  1. USER logs into the server with their username and password.
     - We call POST /api/auth/token/ with username + password.
     - The server returns a JWT (JSON Web Token) -- a long string that proves
       who you are. JWTs are like temporary ID badges.

  2. We READ the Pico's unique hardware ID via USB serial.
     - Every Pico has a unique ID burned into the chip (see provision.py).
     - This ID is how the server identifies this specific physical device.

  3. We REGISTER the Pico on the server.
     - We call POST /api/power/pico-devices/ with:
       - The Pico's unique_id (hardware ID)
       - A human-friendly name (e.g. "Living Room Pico")
     - The Authorization header contains our JWT from step 1.

  4. The server CREATES the device record and returns a device_token.
     - The device_token is a secret string that the Pico will use to
       authenticate its data transmissions.
     - IMPORTANT: The device_token is shown only once! If you lose it,
       you must regenerate it on the server.

  5. We WRITE the device_token to the Pico's secrets.json.
     - Now the Pico has everything it needs: WiFi creds, server URL, and token.
     - On its next boot, it will connect to WiFi and start sending data.

WHY JWT?
--------
JWT (JSON Web Token) is a standard way to handle authentication in web APIs.
Instead of sending username + password with every request, you:
  1. Log in once and get a token (JWT).
  2. Send the token with subsequent requests.
  3. The token expires after a while (security measure).

Our server uses JWT stored in HTTP cookies, but for this CLI tool we use the
token directly in the Authorization header since we are not a browser.
"""

import requests


def login_to_server(api_url, username, password):
    """
    Log into the Django server and get a JWT access token.

    Parameters:
        api_url:   Base URL of the server, e.g. "https://example.com"
        username:  Your Django username
        password:  Your Django password

    Returns:
        The JWT access token string.

    How it works:
        We send a POST request to the token endpoint with credentials.
        The server validates them and returns two tokens:
          - access:  Short-lived token (used for API requests)
          - refresh: Long-lived token (used to get new access tokens)
        We only need the access token since this is a one-time operation.
    """
    # Remove trailing slash for consistent URL building
    api_url = api_url.rstrip("/")
    token_url = f"{api_url}/api/auth/token/"

    try:
        response = requests.post(
            token_url,
            json={"username": username, "password": password},
            timeout=15,
        )
    except requests.ConnectionError:
        raise RuntimeError(
            f"Could not connect to server at {api_url}\n"
            f"\n"
            f"Possible causes:\n"
            f"  - The server is not running\n"
            f"  - The URL is wrong (check for typos)\n"
            f"  - Your computer cannot reach the server (firewall, VPN, etc.)"
        )
    except requests.Timeout:
        raise RuntimeError(
            f"Connection to {api_url} timed out.\n"
            f"The server might be overloaded or unreachable."
        )

    if response.status_code == 200:
        data = response.json()
        # The server returns {"access": "...", "refresh": "..."}
        access_token = data.get("access")
        if access_token:
            return access_token
        # Some servers return the token in cookies instead of the response body.
        # Check cookies as a fallback.
        for cookie in response.cookies:
            if cookie.name == "access_token":
                return cookie.value
        raise RuntimeError(
            "Login succeeded but no access token was found in the response.\n"
            "The server API may have changed."
        )

    elif response.status_code == 401:
        raise RuntimeError(
            "Login failed: invalid username or password.\n"
            "Double-check your credentials and try again."
        )
    else:
        raise RuntimeError(
            f"Login failed with status {response.status_code}.\n"
            f"Response: {response.text[:500]}"
        )


def register_device(api_url, access_token, device_id, device_name=None):
    """
    Register a Pico device on the Django server.

    Parameters:
        api_url:      Base URL of the server
        access_token: JWT from login_to_server()
        device_id:    The Pico's unique hardware ID (hex string)
        device_name:  Optional human-friendly name, e.g. "Kitchen Pico"

    Returns:
        A dict with the server's response, including the device_token.

    The server creates a new device record and generates a unique device_token.
    This token is what the Pico uses to authenticate when sending sensor data.
    """
    api_url = api_url.rstrip("/")
    devices_url = f"{api_url}/api/power/pico-devices/"

    payload = {
        "unique_id": device_id,
    }
    if device_name:
        payload["name"] = device_name

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            devices_url,
            json=payload,
            headers=headers,
            timeout=15,
        )
    except requests.ConnectionError:
        raise RuntimeError(f"Could not connect to {devices_url}")
    except requests.Timeout:
        raise RuntimeError(f"Request to {devices_url} timed out")

    if response.status_code in (200, 201):
        data = response.json()
        device_token = data.get("device_token")
        if not device_token:
            raise RuntimeError(
                "Device was registered but no device_token was returned.\n"
                "Check the server API -- the device_token should be in the response."
            )
        return {
            "device_id": device_id,
            "device_token": device_token,
            "server_response": data,
        }

    elif response.status_code == 400:
        raise RuntimeError(
            f"Registration failed (400 Bad Request).\n"
            f"This Pico may already be registered on the server.\n"
            f"Server response: {response.text[:500]}"
        )
    elif response.status_code == 401:
        raise RuntimeError(
            "Registration failed: authentication error (401).\n"
            "Your login session may have expired. Try again."
        )
    elif response.status_code == 403:
        raise RuntimeError(
            "Registration failed: permission denied (403).\n"
            "Your account may not have permission to register devices."
        )
    else:
        raise RuntimeError(
            f"Registration failed with status {response.status_code}.\n"
            f"Response: {response.text[:500]}"
        )


def register_and_provision(api_url, username, password, port, device_name=None):
    """
    Complete registration flow: login, read device ID, register, write token.

    This is the high-level function called by 'pico-cli register'. It ties
    together the entire registration process:

      1. Log into the server to get a JWT.
      2. Read the Pico's hardware ID via serial.
      3. Register the device on the server.
      4. Write the device_token back to the Pico's secrets.json.

    Parameters:
        api_url:     Base URL of the Django server
        username:    Your Django username
        password:    Your Django password
        port:        Serial port of the Pico
        device_name: Optional human-friendly name

    Returns:
        A dict with registration details.
    """
    # Import here to avoid circular imports
    from .provision import read_device_id, read_current_secrets, write_secrets

    # Step 1: Authenticate with the server
    access_token = login_to_server(api_url, username, password)

    # Step 2: Read the Pico's unique hardware ID
    device_id = read_device_id(port)

    # Step 3: Register on the server
    result = register_device(api_url, access_token, device_id, device_name)
    device_token = result["device_token"]

    # Step 4: Write the token back to the Pico's secrets.json.
    # We merge with existing secrets so we do not overwrite WiFi config, etc.
    try:
        existing_secrets = read_current_secrets(port)
    except Exception:
        existing_secrets = {}

    secrets = {
        **existing_secrets,
        "device_id": device_id,
        "device_token": device_token,
        "server_url": api_url,
    }
    write_secrets(port, secrets)

    return {
        "device_id": device_id,
        "device_token": device_token,
        "port": port,
        "message": (
            "Device registered successfully!\n"
            "\n"
            "IMPORTANT: Save the device_token shown above. It is displayed\n"
            "only once. It has also been written to the Pico's secrets.json.\n"
            "If you lose it, you will need to regenerate it on the server."
        ),
    }
