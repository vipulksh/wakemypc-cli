## v1.0.2 — Default-mode filter for v0.3.1 firmware diagnostics

The wakemypc-firmware v0.3.1 release adds heavier diagnostic
instrumentation: a 5-second main-loop tick, per-message `ws recv`
lines, per-device scan-tick traces, and per-redirect-hop OTA HTTP
traces. Useful for debugging, noisy for everyday use.

This release teaches `wakemypc logs`'s default-mode filter to hide
those new lines so the everyday stream stays readable. Pass
`--debug` to see them all.

**Install / upgrade:**
```
pip install --upgrade git+https://github.com/vipulksh/wakemypc-cli.git
```
