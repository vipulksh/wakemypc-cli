## v1.2.1 — Browser sign-in for `register` (supports "Sign in with Google")

Supersedes the released v1.2.0 token-in-URL design with a loopback
authorization-code exchange (modelled on the OAuth 2.0 native-app pattern in
RFC 8252; not a conformant OAuth 2.0 implementation — no registered client,
PKCE, or scopes).

### New

- **`wakemypc register --oauth`** — sign in via your browser instead of
  passing `--username` / `--password`. The CLI opens `<api-url>/dashboard/cli-auth`,
  the website hands back a short-lived single-use **authorization code** on a
  `127.0.0.1` loopback callback, and the CLI exchanges that code for a JWT
  via `POST /api/jwtauth/cli-exchange/`. Because the website handles the
  actual sign-in, any method the dashboard supports works — including
  **Sign in with Google**. The JWT itself never appears in any URL.
- **`--no-browser`** — pair with `--oauth` on headless / SSH sessions; the
  CLI prints the sign-in URL for you to paste into a browser elsewhere.
- **`--oauth-timeout`** (default `300s`) — how long to wait for you to finish
  signing in before giving up.

### Examples

```bash
# Fresh registration via the browser
wakemypc register --api-url https://wakemypc.com --oauth

# Rotate an existing Pico's token via the browser
wakemypc register --api-url https://wakemypc.com --oauth --rotate

# Headless box: print the URL instead of launching a browser
wakemypc register --api-url https://wakemypc.com --oauth --no-browser
```

### Security notes

- The loopback server binds to `127.0.0.1` only.
- The redirect URL carries a 5-minute single-use authorization code — never
  the JWT. The token is delivered to the CLI in a backend POST response body
  that is not stored in browser history.
- A CSRF `state` nonce is round-tripped through the browser and validated
  before the code is exchanged.
- `--oauth` and `--token` are mutually exclusive (`--token` skips the server;
  `--oauth` exists to talk to it). Username/password registration is
  unchanged.

### Server requirements

This release expects the server to expose `/api/jwtauth/cli-issue-code/` and
`/api/jwtauth/cli-exchange/`, plus the `/dashboard/cli-auth` page. Against
older servers, fall back to `--username` / `--password`.
