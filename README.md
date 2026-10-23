# HTTPS task runner

A manually triggered utility for one HTTPS request from a standard GitHub-hosted Ubuntu runner. Request configuration is held in the `TASK_INPUT` repository secret. Results are encrypted to the operator's public certificate before they enter the job log.

## Limits

- One GET, POST, or PATCH per run; no automatic retries or redirects.
- Normal certificate and hostname verification; no proxy inheritance.
- Three-minute job limit, no schedules, no external Actions, no downloads, no artifacts or caches.
- Empty workflow token permissions.
- Response limit: 128 KiB. A failed or interrupted write has an unknown outcome; reconcile it before starting another run.

## Configuration

`TASK_INPUT` is a JSON object with `url`, optional `method`, optional string-valued `headers`, and optional `body`. URLs must use HTTPS and cannot contain user information or fragments. GET cannot have a body.

`RESPONSE_CERT` is a PEM X.509 public certificate, stored as a repository secret or variable. Keep its private key on your own machine. Do not give this workflow private keys.

Start with an unauthenticated GET. Trigger the workflow manually, retrieve its `ENCRYPTED_RESPONSE:` line, decode the base64 to a DER file, and decrypt locally:

```sh
openssl cms -decrypt -binary -inform DER -in response.der -recip response-cert.pem -inkey response-key.pem
```

Only the encrypted response and fixed local error codes are printed. Remove request secrets after the intended use. Review the source before using a credential and configure only accounts and endpoints you are authorized to access.

## Local checks

```sh
python3 -m unittest -v test_runner.py
```

The tests use mocks and make no external requests. `runner.py` is embedded in the workflow to avoid running a checkout or third-party dependency.
