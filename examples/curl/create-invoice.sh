#!/usr/bin/env bash
# Create a 5 USDT invoice and print the payment link.
#   TGPAY_API_TOKEN=... ./create-invoice.sh
set -euo pipefail
: "${TGPAY_API_TOKEN:?set TGPAY_API_TOKEN}"
BASE="${TGPAY_API_BASE:-https://testnet.tgpaycrypto.com/pay/api}"

curl -sS "$BASE/getMe" -H "TgPayCrypto-API-Token: $TGPAY_API_TOKEN"
echo

curl -sS "$BASE/createInvoice" \
  -H "TgPayCrypto-API-Token: $TGPAY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "asset": "USDT",
    "amount": "5",
    "description": "Order #1001",
    "payload": "order-1001",
    "client_invoice_id": "order-1001"
  }'
echo
