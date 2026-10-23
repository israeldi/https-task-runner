import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch
from urllib.request import Request

import runner


class RunnerTests(unittest.TestCase):
    def spec(self, **values):
        return json.dumps({"url": "https://example.org/status", **values})

    def test_only_https_without_userinfo(self):
        for url in ("http://example.org", "https://user:secret@example.org", "https:///missing", "https://example.org/#fragment", "https://example.org/\nsecret"):
            with self.subTest(url=url), self.assertRaises(runner.SafeFailure):
                runner.validate_spec(self.spec(url=url))
        self.assertEqual(runner.validate_spec(self.spec())["url"], "https://example.org/status")

    def test_methods_and_header_injection(self):
        for extra in ({"method": "DELETE"}, {"headers": {"Authorization": "secret\nInjected: value"}}, {"body": "GET body"}):
            with self.assertRaises(runner.SafeFailure):
                runner.validate_spec(self.spec(**extra))

    def test_redirect_handler_never_follows(self):
        self.assertIsNone(runner.NoRedirect().redirect_request(Request("https://example.org"), None, 302, "", {}, "https://other.example"))

    def test_response_cap_and_no_retry(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b"x" * (runner.LIMIT + 1)
        opener = Mock()
        opener.open.return_value = response
        with patch.object(runner.urllib.request, "build_opener", return_value=opener), self.assertRaises(runner.SafeFailure):
            runner.fetch_response(runner.validate_spec(self.spec()))
        response.read.assert_called_once_with(runner.LIMIT + 1)
        opener.open.assert_called_once()

    def test_no_request_spec_or_response_in_logs(self):
        out = io.StringIO()
        with patch.dict(runner.os.environ, {"TASK_INPUT": self.spec(headers={"Authorization": "Bearer DO_NOT_PRINT"}), "RESPONSE_CERT": "-----BEGIN CERTIFICATE-----\npublic\n-----END CERTIFICATE-----"}), patch.object(runner, "fetch_response", return_value={"http_status": 200, "body": "PRIVATE_RESPONSE"}), patch.object(runner, "encrypt_response", return_value="Y2lwaGVydGV4dA=="), redirect_stdout(out):
            self.assertEqual(runner.main(), 0)
        self.assertEqual(out.getvalue(), "ENCRYPTED_RESPONSE:Y2lwaGVydGV4dA==\n")

    def test_raw_failure_never_printed(self):
        out = io.StringIO()
        with patch.dict(runner.os.environ, {"TASK_INPUT": self.spec(), "RESPONSE_CERT": "-----BEGIN CERTIFICATE-----\npublic\n-----END CERTIFICATE-----"}), patch.object(runner, "fetch_response", side_effect=RuntimeError("DO_NOT_PRINT credentials")), redirect_stdout(out):
            self.assertEqual(runner.main(), 1)
        self.assertNotIn("DO_NOT_PRINT", out.getvalue())

    def test_public_certificate_required_before_request(self):
        with patch.dict(runner.os.environ, {"TASK_INPUT": self.spec(), "RESPONSE_CERT": ""}), patch.object(runner, "fetch_response") as fetch, redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(), 1)
        fetch.assert_not_called()

    def test_encryption_command_and_isolated_environment(self):
        with patch.dict(runner.os.environ, {"TASK_INPUT": "secret-input"}), patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"ciphertext", b"")) as process:
            result = runner.encrypt_response({"http_status": 200, "body": "private"}, "-----BEGIN CERTIFICATE-----\npublic\n-----END CERTIFICATE-----")
        self.assertEqual(result, "Y2lwaGVydGV4dA==")
        args, kwargs = process.call_args
        self.assertEqual(args[0][:8], ["openssl", "cms", "-encrypt", "-aes256", "-binary", "-outform", "DER", args[0][7]])
        self.assertNotIn("TASK_INPUT", kwargs["env"])
        self.assertTrue(kwargs["capture_output"])

    def test_encryption_failure_happens_before_request(self):
        with patch.dict(runner.os.environ, {"TASK_INPUT": self.spec(), "RESPONSE_CERT": "-----BEGIN CERTIFICATE-----\ninvalid\n-----END CERTIFICATE-----"}), patch.object(runner, "encrypt_response", side_effect=runner.SafeFailure("response_encryption_failed")), patch.object(runner, "fetch_response") as fetch, redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(), 1)
        fetch.assert_not_called()

    def test_mutation_rerun_never_requests(self):
        with patch.dict(runner.os.environ, {"TASK_INPUT": self.spec(method="POST", body={}), "RESPONSE_CERT": "-----BEGIN CERTIFICATE-----\npublic\n-----END CERTIFICATE-----", "GITHUB_RUN_ATTEMPT": "2"}), patch.object(runner, "fetch_response") as fetch, redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(), 1)
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
