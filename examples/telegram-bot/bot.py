"""TgPay Crypto Merchant API demo: a Telegram bot that sells access to a
private channel.

/buy creates an invoice priced in US dollars. The buyer pays it with any
cryptocurrency the wallet holds, the app balance is credited in USDT
(`swap_to`), the webhook arrives, the bot checks its signature and sends an
invite. The invite asks to join and the bot lets in only the account that
paid, so access is sold once: /buy never bills it a second time.

Runs against the TESTNET by default: no real money moves.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation

from aiohttp import ClientSession, ClientTimeout, web
from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import ChatJoinRequest, InlineKeyboardButton, InlineKeyboardMarkup, Message

API = os.environ.get("TGPAY_API", "https://testnet.tgpaycrypto.com/pay/api")
TGPAY_TOKEN = os.environ["TGPAY_API_TOKEN"]
# The signature key is the SHA-256 digest of the app's signing secret.
SIGNING_KEY = hashlib.sha256(os.environ["TGPAY_WEBHOOK_SECRET"].encode()).digest()
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
DB_PATH = os.environ.get("DB_PATH", "demo.sqlite3")
PORT = int(os.environ.get("PORT", "8080"))
SOURCE_URL = os.environ.get("SOURCE_URL", "")

PRICE_USD = "1"          # a decimal STRING: the API refuses a JSON number
INVOICE_TTL = 3600       # seconds to pay
INVITE_TTL = 3600        # seconds the invite link lives
MAX_INVOICES_PER_HOUR = 5  # per buyer; createInvoice allows 60 a minute per app

log = logging.getLogger("demo")
bot = Bot(os.environ["BOT_TOKEN"])
dp = Dispatcher()
http: ClientSession  # created in main()

TEXTS = {
    "ru": {
        "start": (
            "Это демо Merchant API кошелька TgPay Crypto в тестовой сети: "
            "настоящие деньги не нужны.\n\n"
            "1. Откройте @tgpaycrypto_testnet_bot и на главном экране нажмите "
            "«Получить тестовую криптовалюту».\n"
            "2. Вернитесь сюда и отправьте /buy.\n\n"
            "Счёт выставлен в долларах, оплатить можно любой криптовалютой, "
            "а продавец получит USDT."
        ),
        "source": "Исходный код: {url}",
        "invoice": "Счёт на ${price} готов. После оплаты пришлю приглашение в закрытый канал.",
        "pay": "Оплатить ${price}",
        "limit": "Слишком много счетов за час. Оплатите уже выставленный или попробуйте позже.",
        "failed": "Не получилось выставить счёт. Попробуйте ещё раз через минуту.",
        "paid": "Оплата получена: {paid}.{credited}\nПриглашение действует час, вступить по нему можете только вы.",
        "have": "Доступ у вас уже есть: вы в канале. Второй раз платить не нужно.",
        "again": "Доступ уже оплачен, новый счёт не нужен. Вот приглашение ещё раз: оно действует час, вступить по нему можете только вы.",
        "join": "Вступить в канал",
        "credited": " Продавцу зачислено {amount} USDT.",
    },
    "en": {
        "start": (
            "This is a demo of the TgPay Crypto Merchant API on the testnet: "
            "no real money is needed.\n\n"
            "1. Open @tgpaycrypto_testnet_bot and tap “Get test coins” on the "
            "home screen.\n"
            "2. Come back and send /buy.\n\n"
            "The invoice is priced in dollars, you pay with any cryptocurrency, "
            "and the seller receives USDT."
        ),
        "source": "Source code: {url}",
        "invoice": "Your ${price} invoice is ready. After the payment I will send an invite to the private channel.",
        "pay": "Pay ${price}",
        "limit": "Too many invoices in an hour. Pay the one you have or try later.",
        "failed": "Could not create the invoice. Try again in a minute.",
        "paid": "Payment received: {paid}.{credited}\nThe invite lasts an hour and only you can join with it.",
        "have": "You already have access: you are in the channel. There is nothing to pay again.",
        "again": "Access is already paid for, no new invoice is needed. Here is the invite again: it lasts an hour and only you can join with it.",
        "join": "Join the channel",
        "credited": " The seller was credited {amount} USDT.",
    },
}
RU_LANGS = ("ru", "uk", "be", "kk", "ky", "uz", "tg", "hy", "az")


def lang_of(message: Message) -> str:
    code = (message.from_user.language_code or "en").split("-")[0].lower()
    return "ru" if code in RU_LANGS else "en"


# ---------------------------------------------------------------- storage

@contextmanager
def db():
    """A connection in autocommit mode, closed on exit."""
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS orders (
                order_id   TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                lang       TEXT NOT NULL,
                status     TEXT NOT NULL,   -- new | paid | delivered
                pay_url    TEXT,
                paid_note  TEXT,
                credited   TEXT,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_orders_user ON orders (user_id, created_at);
            CREATE TABLE IF NOT EXISTS updates (
                update_id  INTEGER PRIMARY KEY,
                seen_at    INTEGER NOT NULL
            );
            """
        )


# ---------------------------------------------------------- Merchant API

async def tgpay(method: str, read: bool = False, **params):
    """Read methods are GET, write methods are POST with a JSON body."""
    url = f"{API}/{method}"
    headers = {"TgPayCrypto-API-Token": TGPAY_TOKEN}
    if read:
        request = http.get(url, params=params, headers=headers)
    else:
        request = http.post(url, json=params, headers=headers)
    async with request as resp:
        data = await resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"{method}: {data.get('error')}")
    return data["result"]


# ------------------------------------------------------------------- bot

@dp.message(CommandStart())
async def start(message: Message) -> None:
    t = TEXTS[lang_of(message)]
    text = t["start"]
    if SOURCE_URL:
        text += "\n\n" + t["source"].format(url=SOURCE_URL)
    await message.answer(text)


@dp.message(Command("buy"))
async def buy(message: Message) -> None:
    lang = lang_of(message)
    t = TEXTS[lang]
    user_id = message.from_user.id
    now = int(time.time())

    # Before any invoice: is the access already sold to this account?
    # A second invoice for it would be a second payment and a refund.
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
    except Exception:
        log.exception("getChatMember failed for %s", user_id)
        await message.answer(t["failed"])   # not known = not billed
        return
    # The channel's own admins are not buyers: they run the purchase to test it.
    if member.status not in ("creator", "administrator"):
        if member.status == "member" or getattr(member, "is_member", False):
            await message.answer(t["have"])
            return
        bought = paid_order(user_id)
        if bought:
            # Paid, but not in the channel (did not join in time, or left).
            if bought["status"] == "paid":
                await deliver_safely(bought["order_id"])   # its first invite
            else:
                await message.answer(t["again"], reply_markup=await invite_keyboard(t))
            return

    with db() as conn:
        # An unpaid invoice that still has time left is shown again,
        # not replaced by a new one.
        open_order = conn.execute(
            "SELECT pay_url FROM orders WHERE user_id = ? AND status = 'new' "
            "AND pay_url IS NOT NULL AND created_at > ? ORDER BY created_at DESC LIMIT 1",
            (user_id, now - INVOICE_TTL + 300),
        ).fetchone()
        recent = conn.execute(
            "SELECT count(*) FROM orders WHERE user_id = ? AND created_at > ?",
            (user_id, now - 3600),
        ).fetchone()[0]

    if open_order:
        pay_url = open_order["pay_url"]
    elif recent >= MAX_INVOICES_PER_HOUR:
        await message.answer(t["limit"])
        return
    else:
        order_id = f"demo-{user_id}-{now}"
        with db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO orders (order_id, user_id, lang, status, created_at) "
                "VALUES (?, ?, ?, 'new', ?)",
                (order_id, user_id, lang, now),
            )
        try:
            invoice = await tgpay(
                "createInvoice",
                currency_type="fiat",
                fiat="USD",
                amount=PRICE_USD,
                swap_to="USDT",               # whatever is paid, the app gets USDT
                description="Demo Club access" if lang == "en" else "Доступ в Demo Club",
                payload=order_id,             # comes back in the webhook as is
                client_invoice_id=order_id,   # a retry returns the same invoice
                expires_in=INVOICE_TTL,
                allow_comments=False,         # the pay screen is the amount, the coins and Pay
                allow_anonymous=False,
            )
        except Exception:
            log.exception("createInvoice failed for %s", order_id)
            await message.answer(t["failed"])
            return
        pay_url = invoice["pay_url"]
        with db() as conn:
            conn.execute("UPDATE orders SET pay_url = ? WHERE order_id = ?", (pay_url, order_id))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t["pay"].format(price=PRICE_USD), url=pay_url),
    ]])
    await message.answer(t["invoice"].format(price=PRICE_USD), reply_markup=keyboard)


# --------------------------------------------------------------- payment

def paid_order(user_id: int):
    """The account's paid order, if it has one: the record of its access."""
    with db() as conn:
        return conn.execute(
            "SELECT order_id, status FROM orders WHERE user_id = ? "
            "AND status IN ('paid', 'delivered') ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()


async def invite_keyboard(t: dict) -> InlineKeyboardMarkup:
    """An invite that ASKS to join: `join_request` below admits only an
    account with a paid order. So the link is safe to send again and useless
    to forward, and one payment is one account in the channel."""
    link = await bot.create_chat_invite_link(
        CHANNEL_ID, creates_join_request=True, expire_date=int(time.time()) + INVITE_TTL
    )
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t["join"], url=link.invite_link),
    ]])


@dp.chat_join_request()
async def join_request(request: ChatJoinRequest) -> None:
    if request.chat.id != CHANNEL_ID:
        return
    if paid_order(request.from_user.id):
        await request.approve()
    else:
        await request.decline()


def same_amount(a: str, b: str) -> bool:
    try:
        return Decimal(a) == Decimal(b)
    except (InvalidOperation, TypeError):
        return False


def settle(invoice: dict, update_id: int | None = None) -> str | None:
    """Mark the order paid. Returns the order id when THIS call paid it.

    A signed body is still not taken on trust: the invoice must be paid,
    priced as we priced it and name an order that waits for a payment. The
    update id and the status change are written in ONE transaction, so a
    crash between them cannot lose the event.
    """
    order_id = invoice.get("payload") or ""
    valid = (
        invoice.get("status") == "paid"
        and invoice.get("currency_type") == "fiat"
        and invoice.get("fiat") == "USD"
        and same_amount(invoice.get("amount"), PRICE_USD)
    )
    paid_note = f"{invoice.get('paid_amount')} {invoice.get('paid_asset')}"
    credited = invoice.get("swapped_output") if invoice.get("swapped_to") == "USDT" else None

    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if update_id is not None:
            try:
                conn.execute(
                    "INSERT INTO updates (update_id, seen_at) VALUES (?, ?)",
                    (update_id, int(time.time())),
                )
            except sqlite3.IntegrityError:
                conn.execute("ROLLBACK")   # a repeated delivery of the same event
                return None
        changed = 0
        if valid:
            changed = conn.execute(
                "UPDATE orders SET status = 'paid', paid_note = ?, credited = ? "
                "WHERE order_id = ? AND status = 'new'",
                (paid_note, credited, order_id),
            ).rowcount
        conn.execute("COMMIT")
    if not valid:
        log.warning("invoice %s does not match an order: %s", invoice.get("invoice_id"), order_id)
    return order_id if changed else None


async def deliver(order_id: str) -> None:
    """Send the invite of a paid order; the order turns `delivered` after it."""
    with db() as conn:
        order = conn.execute(
            "SELECT * FROM orders WHERE order_id = ? AND status = 'paid'", (order_id,)
        ).fetchone()
    if not order:
        return
    t = TEXTS[order["lang"]]
    credited = t["credited"].format(amount=order["credited"]) if order["credited"] else ""
    await bot.send_message(
        order["user_id"],
        t["paid"].format(paid=order["paid_note"], credited=credited),
        reply_markup=await invite_keyboard(t),
    )
    with db() as conn:
        conn.execute(
            "UPDATE orders SET status = 'delivered' WHERE order_id = ? AND status = 'paid'",
            (order_id,),
        )


async def deliver_safely(order_id: str) -> None:
    try:
        await deliver(order_id)
    except Exception:
        # The order stays `paid`; the reconcile loop tries again.
        log.exception("delivery failed for %s", order_id)


async def webhook(request: web.Request) -> web.Response:
    raw = await request.read()   # the RAW bytes: the signature covers them, not re-serialized JSON
    expected = hmac.new(SIGNING_KEY, raw, hashlib.sha256).hexdigest()
    got = request.headers.get("TgPayCrypto-API-Signature", "").strip().lower()
    if not hmac.compare_digest(expected.encode(), got.encode()):
        return web.Response(status=401)

    update = json.loads(raw)
    if update.get("update_type") == "invoice_paid":
        order_id = settle(update["payload"], update_id=update["update_id"])
        if order_id:
            # Answer within the platform's 10 seconds; the invite goes out after.
            asyncio.create_task(deliver_safely(order_id))
    return web.Response(text="ok")


async def reconcile() -> None:
    """Webhook delivery is not guaranteed: every few minutes ask the API which
    invoices are paid, finish undelivered orders and drop old rows."""
    while True:
        await asyncio.sleep(300)
        try:
            paid = await tgpay("getInvoices", read=True, status="paid", count=100)
            for invoice in paid["items"]:
                settle(invoice)
            with db() as conn:
                pending = [r["order_id"] for r in conn.execute(
                    "SELECT order_id FROM orders WHERE status = 'paid'")]
                now = int(time.time())
                # Only unpaid rows age out: a paid order is the record of access.
                conn.execute(
                    "DELETE FROM orders WHERE status = 'new' AND created_at < ?",
                    (now - 30 * 86400,))
                # Deliveries are retried for about two days; keep ids for a week.
                conn.execute("DELETE FROM updates WHERE seen_at < ?", (now - 7 * 86400,))
            for order_id in pending:
                await deliver_safely(order_id)
        except Exception:
            log.exception("reconcile failed")


async def health(_: web.Request) -> web.Response:
    return web.Response(text="ok")


async def main() -> None:
    global http
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    init_db()
    http = ClientSession(timeout=ClientTimeout(total=20))
    app = web.Application(client_max_size=64 * 1024)
    app.router.add_post("/tgpay/webhook", webhook)
    app.router.add_get("/healthz", health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    background = asyncio.create_task(reconcile())
    try:
        # Named explicitly: join requests are not in Telegram's default set.
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        background.cancel()
        await runner.cleanup()
        await http.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
