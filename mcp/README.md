# MCP server

`https://app.tgpaycrypto.com/mcp` — a remote MCP server (Streamable HTTP) for the TgPay Crypto
Merchant API. An AI agent reads the integration docs, creates invoices and subscription plans,
and configures webhooks. Listed in the official MCP Registry as `com.tgpaybot/merchant-api`
([`server.json`](server.json)).

**Auth.** No token needed to start: the `connect` tool returns an approval link, you approve once in
[@tgpaycryptobot](https://t.me/tgpaycryptobot), and `connect_status` hands the agent a **scoped** token
(`read, invoices, subscriptions, webhooks` — it cannot send payouts, refunds or withdrawals). An existing token can be passed in
the `TgPayCrypto-API-Token` header.

## Claude Code

```bash
claude mcp add --transport http tgpaycrypto https://app.tgpaycrypto.com/mcp
```

## Claude.ai / Claude Desktop / ChatGPT

Settings → Connectors → add a custom connector with the URL `https://app.tgpaycrypto.com/mcp`.

## Cursor (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "tgpaycrypto": { "url": "https://app.tgpaycrypto.com/mcp" }
  }
}
```

## VS Code (`.vscode/mcp.json`)

```json
{
  "servers": {
    "tgpaycrypto": { "type": "http", "url": "https://app.tgpaycrypto.com/mcp" }
  }
}
```

Then ask the agent: *"Integrate TgPay Crypto payments into this project — start with get_docs('quickstart')."*
