"""Compute one public synthetic receipt without inference or network access."""

import argparse
from hashlib import sha256
import json
import re
import sys


FIXTURE_NAME = "synthetic-canonical-json-v1"
OPERATION = "canonical_json_sha256"


def canonical_json(value):
    """Encode the bounded fixture format with sorted keys and compact UTF-8."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def build_request(request_id):
    if re.fullmatch(r"[0-9a-f]{32}", request_id) is None:
        raise ValueError("Request ID must contain exactly 32 lowercase hexadecimal digits.")
    return {
        "schema": "cloud-work-request/v1",
        "request_id": request_id,
        "operation": OPERATION,
        "data_scope": "synthetic_public",
        "fixture": FIXTURE_NAME,
    }


def create_receipt(request_id):
    request = build_request(request_id)
    fixture = {"z": 3, "a": ["β", {"y": True, "x": None}], "m": 0}
    canonical = canonical_json(fixture)
    return {
        **request,
        "schema": "cloud-work-receipt/v1",
        "request_sha256": sha256(canonical_json(request)).hexdigest(),
        "output": {
            "canonical_json": canonical.decode("utf-8"),
            "sha256": sha256(canonical).hexdigest(),
            "bytes": len(canonical),
        },
        "executor": "python-stdlib-json-v1",
        "inference": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--request-id", required=True)
    arguments = parser.parse_args()
    try:
        receipt = create_receipt(arguments.request_id)
    except ValueError as error:
        parser.error(str(error))
    sys.stdout.buffer.write(canonical_json(receipt) + b"\n")


if __name__ == "__main__":
    main()
