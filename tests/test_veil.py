import json
import re
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

try:
    import cryptography  # noqa: F401  (only needed for the encrypted vault)
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

from veil import LocalLLMDetector, RuleDetector, Shield
from veil.llm import MockCloudAI
from veil.proxy import make_server

SAMPLE = (Path(__file__).resolve().parent.parent / "examples" / "customer_email.txt").read_text()
SECRETS = ["Sarah", "Tan", "John", "Smith", "sarah.tan@acme-logistics.com", "+65 9123 4567",
           "S1234567D", "4111 1111 1111 1111", "192.168.10.24", "acme-logistics",
           "john.smith@acme-logistics.com"]


def contains(text, needle):
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", text, re.I) is not None


class ShieldTests(unittest.TestCase):
    def test_no_real_value_reaches_the_ai(self):
        masked = Shield().mask(SAMPLE)
        for s in SECRETS:
            self.assertFalse(contains(masked, s), f"{s!r} leaked")

    def test_round_trip_restores_original(self):
        shield = Shield()
        self.assertEqual(shield.unmask(shield.mask(SAMPLE)), SAMPLE)

    def test_same_person_gets_same_fake_everywhere(self):
        shield = Shield()
        masked = shield.mask("John Smith called. Later Mr Smith emailed john.smith@acme.com. John was upset.")
        first, last = shield.tables["first"]["john"], shield.tables["last"]["smith"]
        self.assertEqual(masked.count(first), 2)
        self.assertIn(f"Mr {last}", masked)
        self.assertIn(f"{first.lower()}.{last.lower()}@", masked)

    def test_consistent_across_calls_in_one_session(self):
        shield = Shield()
        a, b = shield.mask("Ask Sarah Tan."), shield.mask("Did Sarah Tan reply?")
        self.assertEqual(a.rstrip(".").split()[1:3], b.split()[1:3])
        self.assertNotIn("Sarah", a + b)

    def test_different_sessions_use_different_fakes(self):
        # a leaked transcript from one session can't be linked to another
        fakes = {Shield().mask("Contact Sarah Tan") for _ in range(8)}
        self.assertGreater(len(fakes), 1)

    def test_gender_is_preserved_for_known_names(self):
        from veil import fakes
        shield = Shield()
        shield.mask("Sarah met John.")
        self.assertIn(shield.tables["first"]["sarah"], fakes.FAKE_FIRST_FEMALE)
        self.assertIn(shield.tables["first"]["john"], fakes.FAKE_FIRST_MALE)

    def test_unmask_handles_case_and_possessive(self):
        shield = Shield()
        shield.mask("John Smith")
        f, l = shield.tables["first"]["john"], shield.tables["last"]["smith"]
        out = shield.unmask(f"{f.upper()} {l}'s order; ask {f.lower()}.")
        self.assertEqual(out, "JOHN Smith's order; ask john.")

    def test_phone_format_preserved(self):
        shield = Shield()
        masked = shield.mask("Call +65 9123 4567 now")
        self.assertRegex(masked, r"Call \+65 9\d{3} \d{4} now")

    def test_fake_card_is_luhn_valid_but_different(self):
        from veil.detect import _luhn_ok
        shield = Shield()
        masked = shield.mask("card 4111 1111 1111 1111")
        digits = re.sub(r"\D", "", masked)
        self.assertNotEqual(digits, "4111111111111111")
        self.assertTrue(_luhn_ok(digits))

    def test_custom_terms(self):
        shield = Shield(detector=RuleDetector(custom_terms=["Project Falcon", "ALLab"]))
        masked = shield.mask("ALLab is running Project Falcon.")
        self.assertNotIn("Falcon", masked)
        self.assertNotIn("ALLab", masked)
        self.assertEqual(shield.unmask(masked), "ALLab is running Project Falcon.")

    @unittest.skipUnless(HAS_CRYPTO, "optional: pip install cryptography")
    def test_encrypted_vault_round_trip(self):
        shield = Shield()
        masked = shield.mask(SAMPLE)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "vault.bin"
            shield.save(path, "pw")
            self.assertNotIn(b"Sarah", path.read_bytes())
            restored = Shield.load(path, "pw")
            self.assertEqual(restored.unmask(masked), SAMPLE)
            with self.assertRaises(Exception):
                Shield.load(path, "wrong-password")

    def test_mock_ai_round_trip(self):
        shield, ai = Shield(), MockCloudAI(log_path=None)
        answer = shield.unmask(ai.chat([{"role": "user", "content": shield.mask(SAMPLE)}]))
        self.assertIn("Sarah Tan", answer)
        self.assertIn("john.smith@acme-logistics.com", answer)
        for s in SECRETS:
            self.assertFalse(contains(ai.received[0], s))


class _JSONServer:
    """Tiny fake HTTP server for testing network pieces offline."""

    def __init__(self, reply_fn):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                out = json.dumps(reply_fn(body)).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


class NetworkTests(unittest.TestCase):
    def test_proxy_masks_and_unmasks(self):
        ai = MockCloudAI(log_path=None)
        server = make_server(ai, Shield(), port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                json.dumps({"model": "x", "messages": [{"role": "user", "content": SAMPLE}]}).encode(),
                {"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as resp:
                answer = json.load(resp)["choices"][0]["message"]["content"]
        finally:
            server.shutdown()
            server.server_close()
        self.assertIn("Sarah Tan", answer)
        for s in SECRETS:
            self.assertFalse(contains(ai.received[0], s))

    def test_local_llm_detector_adds_entities(self):
        # the "self-hosted model" finds a client name the regexes can't know about
        srv = _JSONServer(lambda body: {"choices": [{"message": {"content":
              '{"entities":[{"text":"Globex Corporation","kind":"ORG"}]}'}}]})
        try:
            shield = Shield(detector=LocalLLMDetector(srv.url, "tiny"))
            masked = shield.mask("Sarah Tan from Globex Corporation called.")
        finally:
            srv.httpd.shutdown()
            srv.httpd.server_close()
        self.assertNotIn("Globex", masked)
        self.assertNotIn("Sarah", masked)
        self.assertEqual(shield.unmask(masked), "Sarah Tan from Globex Corporation called.")


if __name__ == "__main__":
    unittest.main()
