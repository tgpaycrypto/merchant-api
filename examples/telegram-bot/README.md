# Telegram bot: sell access to a private channel

A complete bot on [aiogram 3](https://docs.aiogram.dev/) that sells one thing — access to a private
channel — for $1, paid in any cryptocurrency. It runs live on the testnet as
[@tgpaycrypto_demo_bot](https://t.me/tgpaycrypto_demo_bot): no real money is needed to try it.

What happens on `/buy`:

1. The bot asks Telegram whether the account is already in the channel and looks for its paid
   order. Access that is already sold is never billed a second time.
2. Otherwise it creates an invoice priced in US dollars (`currency_type: "fiat"`). The payer picks
   any asset their wallet holds; `swap_to: "USDT"` credits the app balance in USDT whatever was paid.
3. The `invoice_paid` webhook arrives. The bot verifies the signature over the raw body, drops a
   repeated `update_id`, checks that the invoice is paid and priced as the order was, and marks the
   order paid — the update id and the status change in one transaction.
4. The buyer gets an invite button. The link asks to join, and the bot approves the request only
   for an account with a paid order, so a forwarded link lets nobody in and the invite can be sent
   again for free.
5. Every five minutes the bot reads `getInvoices?status=paid` and finishes anything a lost webhook
   left behind. Webhook delivery is retried, but it is not guaranteed.

Orders and seen update ids live in SQLite (`DB_PATH`).

## Run it

You need a bot from [@BotFather](https://t.me/BotFather), a private channel where the bot is an
admin with the right to invite users, and a public HTTPS address that reaches the bot's port.

1. In [@tgpaycrypto_testnet_bot](https://t.me/tgpaycrypto_testnet_bot) open **Merchant API**, create
   an app and copy its token. In the app's **Webhook** section set the URL to
   `https://<your-host>/tgpay/webhook` and create a signing secret (`whsec_…`).
2. Fill in the environment:

   ```bash
   cp .env.example .env    # BOT_TOKEN, TGPAY_API_TOKEN, TGPAY_WEBHOOK_SECRET, CHANNEL_ID
   ```

3. Start it:

   ```bash
   docker compose up -d --build
   ```

   or without Docker (Python ≥ 3.10):

   ```bash
   pip install -r requirements.txt
   set -a; . ./.env; set +a
   python bot.py
   ```

The bot listens on port 8080: `POST /tgpay/webhook` for deliveries, `GET /healthz` for a health
check. The compose file binds it to loopback — put a reverse proxy with TLS in front, or a tunnel
while developing.

To buy, a second Telegram account opens the testnet wallet, taps **Get test coins** on the home
screen and sends `/buy` to your bot. The channel's own admins are always billed: that is how you
test a purchase on an account that is already in the channel.

## Going to production

Set `TGPAY_API=https://app.tgpaycrypto.com/pay/api` and use a token and a signing secret of an app
created in [@tgpaycryptobot](https://t.me/tgpaycryptobot). Nothing else changes.

Fees are taken from what the app receives, never from the payer: a share of each paid invoice, and
the exchange spread when `swap_to` converts the payment. The current figures are in the app under
**Merchant API → your app → Accepting payments** and in the
[documentation](https://docs.tgpaycrypto.com/).
