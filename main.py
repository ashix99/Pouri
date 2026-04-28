from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import contextlib

from telethon import TelegramClient, events

from fx_calculator import (
    UserInputError,
    analyze_message,
    extract_rate_day_only,
    render_result,
)
from pdf_report import build_report_pdf

logging.basicConfig(
    format="[%(levelname)s %(asctime)s] %(name)s: %(message)s",
    level=logging.INFO,
)
LOGGER = logging.getLogger("pouri-fx-bot")

START_MESSAGE = """سلام، به ربات پوری خوش آمدی.

این ربات فقط در چت خصوصی، لیست خرید و فروش ارزی را می‌گیرد و دقیقا طبق فرمت مدنظر شما دو مرحله اجرا می‌کند:

1. مرحله اول همیشه محاسبه می‌شود:
- مجموع فروش واقعی
- مجموع خرید واقعی
- سود/ضرر کلی

2. اگر `RATE_DAY` داخل پیام باشد، مرحله دوم هم ساخته می‌شود:
- جدول کامل هر ردیف
- اختلاف، ساده‌شده، وضعیت
- جمع بدهکار/بستانکار برای خرید و فروش

فرمت قابل قبول:
```
فروش
6م علی 153200
2.5m رضا 149950

خرید
4م سارا 151800
1.75m مهدی 150400

RATE_DAY: 152600
```

اگر `RATE_DAY` را نگذاری، ربات مرحله اول را می‌فرستد و از تو می‌خواهد نرخ روز را جداگانه بفرستی."""

HELP_MESSAGE = """راهنما:

- ربات فقط به پیام متنی در چت خصوصی جواب می‌دهد.
- اگر پیام با `/` شروع شود، به‌عنوان لیست محاسباتی پردازش نمی‌شود.
- هر ردیف باید این سه بخش را داشته باشد:
  مقدار با `m` یا `م` + اسم + نرخ فی ۵ یا ۶ رقمی
- اگر خطی معتبر نباشد، رد می‌شود و دلیلش گزارش می‌شود.
- اگر فقط `RATE_DAY: 152600` بفرستی و قبلش لیست بدون نرخ روز داده باشی، مرحله دوم با همان لیست کامل می‌شود."""

PENDING_MESSAGES: dict[int, str] = {}


def load_dotenv(dotenv_path: str = ".env") -> None:
    env_file = Path(dotenv_path)
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"متغیر محیطی {name} تنظیم نشده است.")
    return value


def create_client() -> tuple[TelegramClient, str]:
    load_dotenv()
    client = TelegramClient(
        os.getenv("SESSION_NAME", "pouri_fx_bot"),
        int(require_env("API_ID")),
        require_env("API_HASH"),
    )
    client.parse_mode = "md"
    return client, require_env("BOT_TOKEN")


def sticker_env_name(kind: str) -> str:
    return f"STICKER_{kind.upper()}"


async def send_optional_sticker(event: events.NewMessage.Event, kind: str) -> None:
    sticker_path = os.getenv(sticker_env_name(kind), "").strip()
    if not sticker_path:
        return

    try:
        await event.reply(file=sticker_path)
    except Exception:
        LOGGER.warning("Failed to send sticker for kind=%s", kind, exc_info=True)


async def send_feedback(event: events.NewMessage.Event, text: str, kind: str) -> None:
    await send_optional_sticker(event, kind)
    await send_long_message(event, text)


async def send_pdf_report(event: events.NewMessage.Event, pdf_path: str) -> None:
    await event.reply(
        message="فایل PDF گزارش",
        file=pdf_path,
        force_document=True,
    )


async def send_long_message(event: events.NewMessage.Event, text: str) -> None:
    if len(text) <= 3900:
        await event.reply(text)
        return

    report_match = split_report_text(text)
    if report_match is not None:
        table_text, tail_text = report_match
        for chunk in split_code_block(table_text):
            await event.reply(chunk)
        for chunk in split_plain_text(tail_text):
            await event.reply(chunk)
        return

    for chunk in split_plain_text(text):
        await event.reply(chunk)


def split_report_text(text: str) -> tuple[str, str] | None:
    marker = "```\n"
    start = text.find(marker)
    if start == -1:
        return None

    end = text.find("\n```", start + len(marker))
    if end == -1:
        return None

    table_text = text[start + len(marker) : end]
    head = text[:start].rstrip()
    tail = text[end + len("\n```") :].strip()
    remainder = "\n".join(part for part in (head, tail) if part)
    return table_text, remainder


def split_code_block(body: str, max_body_size: int = 3300) -> list[str]:
    return [f"```\n{chunk}\n```" for chunk in split_by_lines(body, max_body_size)]


def split_plain_text(text: str, max_body_size: int = 3500) -> list[str]:
    return split_by_lines(text, max_body_size)


def split_by_lines(text: str, max_body_size: int) -> list[str]:
    lines = text.splitlines() or [text]
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0

    for line in lines:
        line_size = len(line) + 1
        if current and current_size + line_size > max_body_size:
            chunks.append("\n".join(current))
            current = [line]
            current_size = line_size
            continue

        current.append(line)
        current_size += line_size

    if current:
        chunks.append("\n".join(current))

    return chunks


def build_error_message(error: Exception) -> str:
    if isinstance(error, UserInputError):
        return f"ورودی قابل پردازش نبود:\n{error}"

    LOGGER.exception("Unhandled error while processing message")
    return "در پردازش پیام خطای غیرمنتظره رخ داد. فرمت ورودی را بررسی کن و دوباره بفرست."


def merge_with_rate_day(base_message: str, rate_message: str) -> str:
    return base_message.rstrip() + "\n" + rate_message.strip()


def choose_response_kind(result_text: str) -> str:
    if "ورودی قابل پردازش نبود" in result_text or "خطای غیرمنتظره" in result_text:
        return "error"
    if "نرخ روز را می‌دهی" in result_text or "ردیف‌های ردشده/مشکوک" in result_text:
        return "warning"
    return "success"


def try_build_pdf_report(result) -> str | None:
    try:
        return build_report_pdf(result)
    except Exception:
        LOGGER.warning("Failed to build PDF report", exc_info=True)
        return None


async def send_result_payload(
    event: events.NewMessage.Event,
    result_text: str,
    kind: str,
    pdf_path: str | None = None,
) -> None:
    try:
        await send_feedback(event, result_text, kind)
        if pdf_path is not None:
            await send_pdf_report(event, pdf_path)
    finally:
        if pdf_path is not None:
            with contextlib.suppress(OSError):
                Path(pdf_path).unlink()


async def main() -> None:
    client, bot_token = create_client()

    @client.on(events.NewMessage(pattern=r"^/start(?:@\w+)?(?:\s+.*)?$"))
    async def start_handler(event: events.NewMessage.Event) -> None:
        if not event.is_private or not event.raw_text:
            return
        await send_feedback(event, START_MESSAGE, "start")

    @client.on(events.NewMessage(pattern=r"^/help(?:@\w+)?(?:\s+.*)?$"))
    async def help_handler(event: events.NewMessage.Event) -> None:
        if not event.is_private or not event.raw_text:
            return
        await send_feedback(event, HELP_MESSAGE, "start")

    @client.on(events.NewMessage(incoming=True, func=lambda event: event.is_private))
    async def message_handler(event: events.NewMessage.Event) -> None:
        if event.message.media is not None or not event.raw_text:
            return

        message_text = event.raw_text.strip()
        if not message_text or message_text.startswith("/"):
            return

        user_id = event.sender_id or 0

        try:
            rate_day_only = extract_rate_day_only(message_text)
            if rate_day_only is not None:
                pending_message = PENDING_MESSAGES.get(user_id)
                if pending_message is None:
                    await send_feedback(
                        event,
                        "برای این نرخ روز، لیست معلقی پیدا نکردم. اول لیست خرید و فروش را بفرست.",
                        "warning",
                    )
                    return

                combined_message = merge_with_rate_day(pending_message, message_text)
                result = analyze_message(combined_message)
                result_text = render_result(result)
                pdf_path = try_build_pdf_report(result)
                PENDING_MESSAGES.pop(user_id, None)
                await send_result_payload(
                    event,
                    result_text,
                    choose_response_kind(result_text),
                    pdf_path,
                )
                return

            result = analyze_message(message_text)
            result_text = render_result(result)
            pdf_path = try_build_pdf_report(result)

            if result.needs_rate_day:
                PENDING_MESSAGES[user_id] = message_text
            else:
                PENDING_MESSAGES.pop(user_id, None)

            await send_result_payload(
                event,
                result_text,
                choose_response_kind(result_text),
                pdf_path,
            )
        except Exception as error:
            await send_feedback(event, build_error_message(error), "error")

    await client.start(bot_token=bot_token)
    me = await client.get_me()
    LOGGER.info("Bot is running as @%s", getattr(me, "username", "unknown"))
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        LOGGER.info("Bot stopped by keyboard interrupt")
