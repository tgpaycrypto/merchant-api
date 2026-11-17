"""Create an invoice and print its payment link. Python >= 3.9, standard library only.

    TGPAY_API_TOKEN=... python create_invoice.py
"""
import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("TGPAY_API_BASE", "https://testnet.tgpaycrypto.com/pay/api")
TOKEN = os.environ["TGPAY_API_TOKEN"]


def call(method, body=None):
    req = urllib.request.Request(
        f"{BASE}/{method}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"TgPayCrypto-API-Token": TOKEN, "Content-Type": "application/json",
                 "User-Agent": "tgpaycrypto-example/1.0"},
        method="POST" if body is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as err:
        try:
            data = json.load(err)
        except ValueError:
            raise RuntimeError(f"{method}: HTTP {err.code}") from None
    if not data.get("ok"):
        raise RuntimeError(f"{method}: {data['error']['code']} {data['error']['name']}")
    return data["result"]


if __name__ == "__main__":
    print("app:", call("getMe"))
    invoice = call("createInvoice", {
        "asset": "USDT",
        "amount": "5",                     # decimal string, major units
        "description": "Order #1001",
        "payload": "order-1001",           # echoed back in the webhook
        "client_invoice_id": "order-1001", # makes retries safe
    })
    print("invoice", invoice["invoice_id"], invoice["status"])
    print("pay link:", invoice["mini_app_invoice_url"])
