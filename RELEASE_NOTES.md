## v1.2.0 - Browser sign-in for `register` (supports "Sign in with Google")

### New

- **`wakemypc register --oauth`** — sign in via your browser instead of passing
  `--username` / `--password`. The CLI opens `<api-url>/dashboard/cli-auth`,
  captures the JWT on a local `127.0.0.1` loopback callback, and then runs the
  normal Pico registration (or rotation, with `--rotate`) in one go. Because
  the website handles the actual sign-in, any method the dashboard supports
  works — including **Sign in with Google**.
- **`--no-browser`** — pair with `--oauth` on headless / SSH sessions; the CLI
  prints the sign-in URL for you to paste into a browser elsewhere instead of
  trying to launch one locally.
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

### Notes

- `--oauth` and `--token` are mutually exclusive (`--token` skips the server;
  `--oauth` exists to talk to it).
- The loopback server binds to `127.0.0.1` only and validates a CSRF `state`
  parameter on the callback, so other machines on the LAN can't deliver a
  token to your CLI.
- Username/password registration (`--username` / `--password`) is unchanged.

### Internal / release engineering

No user-facing change, but contributors should know:

- Releases are now cut automatically when a PR that bumps `pyproject.toml`
  and `RELEASE_NOTES.md` is merged to `main`. The `Release CLI` workflow
  pushes the `vX.Y.Z` tag, builds the wheel + sdist, and creates the GitHub
  Release using `RELEASE_NOTES.md` as the body. PyPI publish then runs on
  that workflow's completion.
- Manually pushing a tag (`git push origin vX.Y.Z`) still works as an
  escape hatch and follows the same path from "build" onward.
- Both workflows are idempotent: a push to `main` that doesn't bump the
  version is a no-op (no failed CI), and re-running publish for a version
  already on PyPI is a no-op.
