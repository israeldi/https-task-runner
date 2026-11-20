"""Check fixed bytes, request binding, and the closed CLI input surface."""

import json
from pathlib import Path
import runpy
import subprocess
import sys
import unittest


WORKER_PATH = Path(__file__).with_name("worker.py")
WORKER = runpy.run_path(str(WORKER_PATH))
ID = "0123456789abcdef0123456789abcdef"


class WorkerTests(unittest.TestCase):
    def run_worker(self, *args):
        return subprocess.run(
            [sys.executable, "-I", "-B", str(WORKER_PATH), *args],
            capture_output=True, check=False, timeout=4,
        )

    def test_canonical_fixture_bytes_and_digest(self):
        receipt = WORKER["create_receipt"](ID)
        self.assertEqual(receipt["output"], {
            "canonical_json": '{"a":["β",{"x":null,"y":true}],"m":0,"z":3}',
            "sha256": "f8da18c39cbe396c3c5e481053a39d58927926ced5404f072d2d166d74bde696",
            "bytes": 44,
        })

    def test_request_definition_and_binding(self):
        request = WORKER["build_request"](ID)
        self.assertEqual(request, {
            "schema": "cloud-work-request/v1", "request_id": ID,
            "operation": "canonical_json_sha256", "data_scope": "synthetic_public",
            "fixture": "synthetic-canonical-json-v1",
        })
        receipt = WORKER["create_receipt"](ID)
        self.assertEqual(receipt["request_sha256"],
                         "c84a6ce279f75a31e505e42f7f9ffb4a7998efa7e5cfc24c1c1a400353df638f")

    def test_alternate_request_has_same_fixture_and_distinct_binding(self):
        first = WORKER["create_receipt"](ID)
        second = WORKER["create_receipt"]("0" * 32)
        self.assertNotEqual(first["request_sha256"], second["request_sha256"])
        self.assertEqual(first["output"], second["output"])

    def test_cli_is_repeatable_and_reports_no_inference(self):
        first = self.run_worker("--request-id", ID)
        second = self.run_worker("--request-id", ID)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(len(first.stdout.splitlines()), 1)
        self.assertEqual(first.stderr, b"")
        receipt = json.loads(first.stdout)
        self.assertEqual(receipt, WORKER["create_receipt"](ID))
        self.assertEqual(receipt["executor"], "python-stdlib-json-v1")
        self.assertIs(receipt["inference"], False)

    def test_wrong_request_ids_exit_without_receipt(self):
        for value in ("", ID[:-1], ID.upper(), "https://example.invalid/", ID + "\n"):
            with self.subTest(value=value):
                attempt = self.run_worker("--request-id", value)
                self.assertEqual(attempt.returncode, 2)
                self.assertEqual(attempt.stdout, b"")

    def test_arbitrary_input_flags_are_refused(self):
        for flag in ("--input", "--url", "--file"):
            with self.subTest(flag=flag):
                attempt = self.run_worker("--request-id", ID, flag, "test")
                self.assertEqual(attempt.returncode, 2)
                self.assertEqual(attempt.stdout, b"")


if __name__ == "__main__":
    unittest.main()
