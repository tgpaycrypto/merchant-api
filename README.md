# TgPay Crypto Merchant API

Accept crypto payments inside Telegram. Payers pay from their
[@tgpaycryptobot](https://t.me/tgpaycryptobot) wallet in a couple of taps;
your app balance is credited and your server gets a signed webhook.

- **Invoices** — fixed or open amount, priced in crypto or fiat, one link or many payments
- **Subscriptions** — recurring plans billed from the payer's wallet
- **Webhooks** — HMAC-SHA256 signed, retried, deduplicated by `update_id`
- **Payouts** — transfers to Telegram users, checks, on-chain withdrawals
- **MCP server** — let an AI agent integrate the API for you

Assets: USDT, USDC, GRAM, BTC, ETH, SOL, TRX, BNB, LTC, DOGE (live list: `getCurrencies`).

| | |
|---|---|
| Documentation | https://docs.tgpaycrypto.com/ |
| OpenAPI spec | [`openapi.json`](openapi.json) · [live](https://docs.tgpaycrypto.com/crypto-pay-openapi.json) |
| Production API | `https://app.tgpaycrypto.com/pay/api` |
| Testnet API | `https://testnet.tgpaycrypto.com/pay/api` (coins with no value, bot [@tgpaycrypto_testnet_bot](https://t.me/tgpaycrypto_testnet_bot)) |
| MCP server | `https://app.tgpaycrypto.com/mcp` — see [`mcp/`](mcp/) |

## Quickstart

1. Open [@tgpaycryptobot](https://t.me/tgpaycryptobot) → **Merchant API** → create an app and copy its token.
   Start on testnet: the same flow in [@tgpaycrypto_testnet_bot](https://t.me/tgpaycrypto_testnet_bot).
2. Keep the token server-side:

   ```bash
   export TGPAY_API_TOKEN=...            # never commit it
   export TGPAY_API_BASE=https://testnet.tgpaycrypto.com/pay/api
   ```

3. Create an invoice:

   ```bash
   curl -s "$TGPAY_API_BASE/createInvoice" \
     -H "TgPayCrypto-API-Token: $TGPAY_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"asset":"USDT","amount":"5","description":"Order #1001","client_invoice_id":"order-1001"}'
   ```

   Send the payer `result.mini_app_invoice_url`.

4. Set your webhook URL (`updateApp {"webhook_url": "https://…"}`) and verify every delivery — see
   [`examples/`](examples/).

## Conventions

- Every response is `{"ok": true, "result": …}` or `{"ok": false, "error": {"code": 401, "name": "unauthorized"}}`.
- Amounts are **decimal strings in major units** (`"5"` = 5 USDT) — never floats.
- Write methods are `POST` with a JSON body; read methods are `GET` with query parameters.
- `client_invoice_id` makes `createInvoice` safe to retry: a repeat returns the existing invoice.

## Webhook signature

Header `TgPayCrypto-API-Signature` = lowercase hex HMAC-SHA256 of the **raw request body**, keyed with the
raw SHA-256 digest of the app's signing secret (`whsec_…`) if you created one, otherwise of the app's
primary API token.

```python
import hashlib, hmac, re
def verify(secret: str, raw_body: bytes, signature: str) -> bool:
    got = (signature or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", got):
        return False
    key = hashlib.sha256(secret.encode()).digest()
    return hmac.compare_digest(hmac.new(key, raw_body, hashlib.sha256).digest(), bytes.fromhex(got))
```

Respond `2xx` quickly and dedupe on `update_id` — failed deliveries are retried.

## Examples

| | create an invoice | webhook receiver |
|---|---|---|
| curl | [`examples/curl/create-invoice.sh`](examples/curl/create-invoice.sh) | — |
| Node.js ≥ 18 | [`examples/node/create-invoice.mjs`](examples/node/create-invoice.mjs) | [`examples/node/webhook-server.mjs`](examples/node/webhook-server.mjs) |
| Python ≥ 3.9 | [`examples/python/create_invoice.py`](examples/python/create_invoice.py) | [`examples/python/webhook_server.py`](examples/python/webhook_server.py) |

No dependencies — standard library only.

## Support

- Telegram: [@tgpaycryptobot](https://t.me/tgpaycryptobot) · news: [@tgpaycrypto_en](https://t.me/tgpaycrypto_en)
- Security reports: see [SECURITY.md](SECURITY.md)

Examples are MIT-licensed. The TgPay Crypto service itself is governed by its
[terms](https://tgpaycrypto.com/en/terms/).
