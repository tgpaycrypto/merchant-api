// Create an invoice and print its payment link. Node.js >= 18, no dependencies.
//   TGPAY_API_TOKEN=... node create-invoice.mjs
const BASE = process.env.TGPAY_API_BASE ?? "https://testnet.tgpaycrypto.com/pay/api";
const TOKEN = process.env.TGPAY_API_TOKEN;
if (!TOKEN) throw new Error("set TGPAY_API_TOKEN");

async function call(method, body) {
  const res = await fetch(`${BASE}/${method}`, {
    method: body ? "POST" : "GET",
    headers: { "TgPayCrypto-API-Token": TOKEN, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!data.ok) throw new Error(`${method}: ${data.error.code} ${data.error.name}`);
  return data.result;
}

const me = await call("getMe");
console.log("app:", me.name ?? me);

const invoice = await call("createInvoice", {
  asset: "USDT",
  amount: "5", // decimal string, major units
  description: "Order #1001",
  payload: "order-1001", // echoed back in the webhook
  client_invoice_id: "order-1001", // makes retries safe
});
console.log("invoice", invoice.invoice_id, invoice.status);
console.log("pay link:", invoice.mini_app_invoice_url);
