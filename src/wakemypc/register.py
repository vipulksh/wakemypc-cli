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

import http.server
import secrets
import socketserver
import threading
import urllib.parse
import webbrowser

import requests


def oauth_login_via_browser(api_url, timeout=300, open_browser=True):
    """
    Browser-based ("loopback") OAuth-style login. Returns the JWT access token.

    HOW IT WORKS  (loopback authorization-code exchange, modelled on RFC 8252)
    --------------------------------------------------------------------------
      1. We bind a one-shot HTTP server on http://127.0.0.1:<random-free-port>.
      2. We open the user's browser at <api_url>/cli-auth?... passing
         our loopback URL as redirect_uri and a fresh CSRF state token.
      3. The browser-side React page (frontend/src/pages/CliAuth.jsx) handles
         the actual sign-in flow (username/password OR "Sign in with Google"),
         asks the server for a single-use authorization code, then redirects
         to  redirect_uri?code=<code>&state=<state>.
      4. Our local server captures code + state from that callback URL, hands
         a "you can close this tab" page back to the browser, then shuts down.
      5. We compare the returned state to the one we generated. If it matches,
         we POST the code to <api_url>/api/jwtauth/cli-exchange/, which
         atomically consumes the code and returns the JWT access token in the
         response body. The token never appears in any URL.

    WHY A CODE INSTEAD OF A TOKEN IN THE URL
    ----------------------------------------
    URLs end up in browser history, Referer headers, and screen-recordings.
    A short-lived (5-minute) single-use code is much safer than a 15-minute
    JWT in those places: by the time anyone could replay the URL, the code
    has already been consumed by the legitimate CLI run. This is the same
    pattern gh / gcloud / aws sso use.

    Parameters:
        api_url:      Base URL of the website (e.g. https://wakemypc.com)
        timeout:      Seconds to wait for the user to finish signing in.
        open_browser: If False, just print the URL instead of opening it.
                      Useful for headless / SSH sessions; the user can paste
                      the URL into a browser on another machine.

    Returns:
        The JWT access token string.
    """
    api_url = api_url.rstrip("/")
    state = secrets.token_urlsafe(32)

    captured = {}
    done = threading.Event()

    class _CallbackHandler(http.server.BaseHTTPRequestHandler):
        # Silence the default per-request access log so it doesn't pollute
        # the CLI output the user is staring at.
        def log_message(self, *args, **kwargs):
            return

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/callback":
                # Anything else (favicon.ico, /, ...) gets a 404 so we
                # don't accidentally accept codes delivered to the wrong path.
                self.send_response(404)
                self.end_headers()
                return
            qs = urllib.parse.parse_qs(parsed.query)
            captured["code"] = (qs.get("code") or [None])[0]
            captured["state"] = (qs.get("state") or [None])[0]
            captured["error"] = (qs.get("error") or [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            ok = bool(captured["code"]) and not captured["error"]
            if ok:
                body = (
                    "<!doctype html><html><body style='font-family:system-ui;"
                    "max-width:32rem;margin:4rem auto;text-align:center'>"
                    "<h2>Authentication successful</h2>"
                    "<p>You can close this tab and return to your terminal.</p>"
                    "</body></html>"
                )
            else:
                body = (
                    "<!doctype html><html><body style='font-family:system-ui;"
                    "max-width:32rem;margin:4rem auto;text-align:center'>"
                    "<h2>Authentication failed</h2>"
                    "<p>No code was returned. Check the terminal for details.</p>"
                    "</body></html>"
                )
            self.wfile.write(body.encode("utf-8"))
            done.set()

    # Port 0 -> kernel hands us a random free port. Bind to 127.0.0.1 only
    # so other machines on the LAN can't hit our callback.
    httpd = socketserver.TCPServer(("127.0.0.1", 0), _CallbackHandler)
    port = httpd.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}/callback"

    auth_url = (
        f"{api_url}/cli-auth?"
        f"redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
        f"&state={urllib.parse.quote(state, safe='')}"
    )

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    try:
        opened = False
        if open_browser:
            try:
                opened = webbrowser.open(auth_url)
            except Exception:
                opened = False
        if not opened:
            # webbrowser.open returns False on headless systems with no
            # browser configured. Print the URL so the user can paste it.
            print(
                f"Open this URL in a browser to sign in:\n  {auth_url}",
                flush=True,
            )

        if not done.wait(timeout=timeout):
            raise RuntimeError(
                f"Timed out after {timeout}s waiting for browser sign-in.\n"
                "If the browser did not open, copy the URL printed above and\n"
                "paste it into a browser manually."
            )

        if captured.get("error"):
            raise RuntimeError(
                f"Browser sign-in reported an error: {captured['error']}"
            )

        if captured.get("state") != state:
            # Mismatched state means the callback didn't come from the page
            # we sent the user to -- treat this as a CSRF / replay attempt.
            raise RuntimeError(
                "State mismatch in OAuth callback -- aborting for safety.\n"
                "Try again; if this keeps happening, the cli-auth page on the\n"
                "server is misconfigured."
            )

        code = captured.get("code")
        if not code:
            raise RuntimeError(
                "Browser sign-in completed but no auth code was returned."
            )
    finally:
        httpd.shutdown()
        httpd.server_close()

    # Exchange the code for the actual JWT. The token comes back in the
    # response body (not in a URL), and the code is single-use on the server
    # so this is safe to do over HTTPS.
    exchange_url = f"{api_url}/api/jwtauth/cli-exchange/"
    try:
        response = requests.post(
            exchange_url,
            json={"code": code},
            timeout=15,
        )
    except requests.ConnectionError:
        raise RuntimeError(
            f"Could not reach {exchange_url} to exchange the auth code."
        )
    except requests.Timeout:
        raise RuntimeError(f"Request to {exchange_url} timed out.")

    if response.status_code != 200:
        try:
            detail = response.json().get("detail", response.text[:200])
        except ValueError:
            detail = response.text[:200]
        raise RuntimeError(
            f"Code exchange failed (status {response.status_code}): {detail}"
        )

    access_token = response.json().get("access")
    if not access_token:
        raise RuntimeError(
            "Code exchange succeeded but no access token was in the response."
        )
    return access_token


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
    token_url = f"{api_url}/api/jwtauth/login/"

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
        api_url:      Base URL of the website (e.g. https://example.com)
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
        if "name" in response.json():
            # Server response: {"name":["This field is required."]}
            raise RuntimeError(
                f"Registration failed (400 Bad Request).\n"
                f"Device name is required.\n"
                f"Server response: {response.text[:500]}\n"
                f"Pass --name to provide a name for this pico device."
            )
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


def find_pico_by_unique_id(api_url, access_token, unique_id):
    """
    Look up an already-registered Pico by its hardware unique_id and
    return the public_id the server assigned it.

    The rotate-token endpoint is keyed on public_id (the short hash that
    appears in URLs), but the only ID the Pico knows about itself is the
    hardware unique_id. We bridge the two by listing the user's Picos
    and matching by unique_id. The user only sees their own + shared
    Picos in this list, so this also doubles as an "ownership" check --
    if no match is found, either the Pico isn't registered to this user
    or hasn't been registered at all, and the caller should fall back
    to a fresh register.

    Returns the public_id string, or None if not found.
    """
    api_url = api_url.rstrip("/")
    list_url = f"{api_url}/api/power/pico-devices/"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.get(list_url, headers=headers, timeout=15)
    except requests.ConnectionError:
        raise RuntimeError(f"Could not connect to {list_url}")
    except requests.Timeout:
        raise RuntimeError(f"Request to {list_url} timed out")

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to list Picos (status {response.status_code}).\n"
            f"Response: {response.text[:500]}"
        )

    # The list endpoint returns either a paginated envelope or a plain
    # list depending on how DRF is configured. Handle both.
    data = response.json()
    picos = data.get("results", data) if isinstance(data, dict) else data
    for p in picos or []:
        if p.get("unique_id") == unique_id:
            return p.get("public_id")
    return None


def rotate_token_for_pico(api_url, access_token, public_id):
    """
    Hit the server's rotate-token action for an already-registered Pico.

    The server invalidates the old encrypted token and returns a fresh
    raw token. This is the same endpoint the dashboard's "Rotate Token"
    button uses; we exposed it on the CLI so a user with USB access can
    rotate + reprovision in one step without bouncing through the web UI.

    Returns the new raw token string.
    """
    api_url = api_url.rstrip("/")
    rotate_url = f"{api_url}/api/power/pico-devices/{public_id}/rotate-token/"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.post(rotate_url, headers=headers, timeout=15)
    except requests.ConnectionError:
        raise RuntimeError(f"Could not connect to {rotate_url}")
    except requests.Timeout:
        raise RuntimeError(f"Request to {rotate_url} timed out")

    if response.status_code in (200, 201):
        data = response.json()
        token = data.get("device_token")
        if not token:
            raise RuntimeError(
                "rotate-token returned no device_token. Server response:\n"
                f"{response.text[:500]}"
            )
        return token

    if response.status_code == 403:
        raise RuntimeError(
            "Cannot rotate this Pico's token: only the owner can do that.\n"
            "If this is your Pico, log in with the owner's credentials."
        )

    raise RuntimeError(
        f"Token rotation failed with status {response.status_code}.\n"
        f"Response: {response.text[:500]}"
    )


def register_and_provision(
    api_url,
    username,
    password,
    port,
    device_name=None,
    rotate=False,
    manual_token=None,
    use_oauth=False,
    oauth_open_browser=True,
    oauth_timeout=300,
):
    """
    Complete registration flow: login, read device ID, register, write token.

    This is the high-level function called by 'wakemypc register'. It ties
    together the entire registration process:

      1. Authenticate with the server. Either:
           - use_oauth=True   -> open the website's /cli-auth page
                                  in a browser, capture the JWT via a local
                                  loopback callback (supports password OR
                                  "Sign in with Google").
           - default           -> POST username + password to /api/jwtauth/login/.
      2. Read the Pico's hardware ID via serial.
      3. Either:
           - rotate=True   -> rotate the existing Pico's token on the server
           - manual_token  -> skip the server entirely; trust the caller's token
           - default       -> register the Pico fresh on the server
      4. Write the resulting device_token back to the Pico's secrets.json.

    Parameters:
        api_url:            Base URL of the website (e.g. https://example.com)
        username:           Your username (ignored when manual_token or
                            use_oauth is set).
        password:           Your password (ignored when manual_token or
                            use_oauth is set).
        port:               Serial port of the Pico.
        device_name:        Optional human-friendly name (ignored on rotate).
        rotate:             If True, rotate an already-registered Pico's token
                            (server invalidates the old token, returns a new
                            one).
        manual_token:       If set, skip all server calls and just write this
                            device_token to the Pico. Use when you've already
                            obtained a token via the dashboard's rotate flow.
        use_oauth:          If True, get the JWT via the browser-based OAuth
                            flow instead of username/password.
        oauth_open_browser: With use_oauth=True, whether to attempt to launch
                            a browser. False prints the URL for manual paste
                            (useful over SSH).
        oauth_timeout:      With use_oauth=True, seconds to wait for the user
                            to complete sign-in.

    Returns:
        A dict with registration details.
    """
    # Import here to avoid circular imports
    from .provision import read_device_id, read_current_secrets, write_secrets

    # Step 2 always runs -- we need the hardware ID either to register a
    # new device or to look up an existing one for rotation, and we need
    # it as device_id when writing secrets.json.
    device_id = read_device_id(port)

    if manual_token:
        # Offline path: don't touch the server. Useful when the user
        # rotated via the dashboard and just wants to push the resulting
        # token to the Pico over USB.
        device_token = manual_token
        action_summary = "Token written from --token argument (no server call)."
    else:
        if use_oauth:
            access_token = oauth_login_via_browser(
                api_url,
                timeout=oauth_timeout,
                open_browser=oauth_open_browser,
            )
        else:
            access_token = login_to_server(api_url, username, password)

        if rotate:
            public_id = find_pico_by_unique_id(api_url, access_token, device_id)
            if not public_id:
                raise RuntimeError(
                    f"No Pico with unique_id={device_id[:16]}... is registered\n"
                    "to your account. Run without --rotate to register fresh."
                )
            device_token = rotate_token_for_pico(api_url, access_token, public_id)
            action_summary = (
                "Token rotated. The previous token is now invalid -- any other\n"
                "device or process using it will need to be re-provisioned."
            )
        else:
            result = register_device(api_url, access_token, device_id, device_name)
            device_token = result["device_token"]
            action_summary = (
                "Device registered successfully!\n"
                "\n"
                "IMPORTANT: Save the device_token shown above. It is displayed\n"
                "only once. It has also been written to the Pico's secrets.json.\n"
                "If you lose it, you will need to regenerate it on the server."
            )

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
    }
    write_secrets(port, secrets)

    return {
        "device_id": device_id,
        "device_token": device_token,
        "port": port,
        "message": action_summary,
    }
