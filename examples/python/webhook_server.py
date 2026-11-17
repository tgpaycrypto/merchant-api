"""Minimal webhook receiver with signature verification. Python >= 3.9, standard library only.

    TGPAY_WEBHOOK_SECRET=whsec_... python webhook_server.py

Create a signing secret in @tgpaycryptobot -> Merchant API -> your app -> Webhook.
(Without one, deliveries are signed with the app's primary API token.)
"""
import hashlib
import hmac
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 1024 * 1024
HEX64 = re.compile(r"[0-9a-f]{64}")


def signing_key(secret: str) -> bytes:
    return hashlib.sha256(secret.encode()).digest()


def verify(key: bytes, raw_body: bytes, signature: str) -> bool:
    got = (signature or "").strip().lower()
    if not HEX64.fullmatch(got):  # anything else is not a signature
        return False
    expected = hmac.new(key, raw_body, hashlib.sha256).digest()
    return hmac.compare_digest(expected, bytes.fromhex(got))


# In production replace this with a database table keyed by update_id:
# insert the id FIRST (unique key), acknowledge, then process.
SEEN = set()


def handle(update: dict) -> None:
    if update["update_id"] in SEEN:  # retries keep the same update_id
        return
    SEEN.add(update["update_id"])
    if update.get("update_type") == "invoice_paid":
        inv = update["payload"]
        # Before fulfilling: check the paid amount and asset against YOUR order.
        print("paid: invoice", inv["invoice_id"], "payload =", inv.get("payload"), flush=True)
    else:
        print("update:", update.get("update_type"), flush=True)


class Handler(BaseHTTPRequestHandler):
    key = b""
    timeout = 10  # an idle connection cannot hold a worker forever

    def _reply(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._reply(400)
        if length < 0:
            return self._reply(400)
        if length > MAX_BODY:
            return self._reply(413)
        raw = self.rfile.read(length)  # verify the RAW bytes, before json.loads
        if not verify(self.key, raw, self.headers.get("TgPayCrypto-API-Signature", "")):
            return self._reply(401)
        try:
            update = json.loads(raw)
            if not isinstance(update, dict) or "update_id" not in update:
                raise ValueError("no update_id")
        except ValueError:
            return self._reply(400)
        self._reply(200)  # a 2xx acknowledges the delivery
        try:
            handle(update)
        except Exception as err:  # never let one update take the server down
            print("handler failed:", err, flush=True)


if __name__ == "__main__":
    Handler.key = signing_key(os.environ["TGPAY_WEBHOOK_SECRET"])
    ThreadingHTTPServer(("", int(os.environ.get("PORT", 8080))), Handler).serve_forever()
