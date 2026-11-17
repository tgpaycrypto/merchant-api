// Minimal webhook receiver with signature verification. Node.js >= 18, no dependencies.
//   TGPAY_WEBHOOK_SECRET=whsec_... node webhook-server.mjs
// Create a signing secret in @tgpaycryptobot -> Merchant API -> your app -> Webhook.
// (Without one, deliveries are signed with the app's primary API token.)
import crypto from "node:crypto";
import http from "node:http";

const SECRET = process.env.TGPAY_WEBHOOK_SECRET;
if (!SECRET) throw new Error("set TGPAY_WEBHOOK_SECRET");
const KEY = crypto.createHash("sha256").update(SECRET).digest();
const MAX_BODY = 1024 * 1024;

export function verify(rawBody, signature) {
  const got = String(signature ?? "").trim().toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(got)) return false; // anything else is not a signature
  const expected = crypto.createHmac("sha256", KEY).update(rawBody).digest();
  return crypto.timingSafeEqual(expected, Buffer.from(got, "hex"));
}

// In production replace this with a database table keyed by update_id:
// insert the id FIRST (unique key), acknowledge, then process.
const seen = new Set();

function handle(update) {
  if (seen.has(update.update_id)) return; // retries keep the same update_id
  seen.add(update.update_id);
  if (update.update_type === "invoice_paid") {
    const inv = update.payload;
    // Before fulfilling: check the paid amount and asset against YOUR order.
    console.log(`paid: invoice ${inv.invoice_id} payload=${inv.payload} ${inv.paid_amount ?? inv.amount} ${inv.paid_asset ?? inv.asset}`);
  } else {
    console.log("update:", update.update_type);
  }
}

const server = http.createServer((req, res) => {
  if (req.method !== "POST") return void res.writeHead(405).end();
  const chunks = [];
  let size = 0;
  req.on("data", (c) => {
    size += c.length;
    if (size > MAX_BODY) {
      res.writeHead(413).end();
      req.destroy();
      return;
    }
    chunks.push(c);
  });
  req.on("end", () => {
    if (res.writableEnded) return;
    const raw = Buffer.concat(chunks); // verify the RAW bytes, before JSON.parse
    if (!verify(raw, req.headers["tgpaycrypto-api-signature"])) {
      return void res.writeHead(401).end();
    }
    let update;
    try {
      update = JSON.parse(raw);
    } catch {
      return void res.writeHead(400).end();
    }
    if (typeof update?.update_id !== "number" && typeof update?.update_id !== "string") {
      return void res.writeHead(400).end();
    }
    res.writeHead(200).end(); // a 2xx acknowledges the delivery
    try {
      handle(update);
    } catch (err) {
      console.error("handler failed:", err);
    }
  });
});

server.listen(process.env.PORT ?? 8080, () => console.log("listening"));
