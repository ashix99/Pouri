from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, getcontext
import re
from typing import Iterable

getcontext().prec = 50

DISPLAY_QUANT = Decimal("0.00000001")
THOUSAND = Decimal("1000")
MILLION = Decimal("1000000")
ABNORMAL_TOTAL_LIMIT = Decimal("5")

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

RATE_MIN = 10000
RATE_MAX = 200000

CTRL_WS_PATTERN = re.compile(r"[\u200C\u200D\u2060\u00A0]")
SPACE_PATTERN = re.compile(r"\s+")
THOUSANDS_SEPARATOR_PATTERN = re.compile(r"(?<=\d)[,.\u066C\u2009\u202F ](?=\d{3}(?:\D|$))")
AMOUNT_TOKEN = re.compile(r"(?P<val>\d+(?:[.,٫]\d+)?)(?P<suf>[mM\u0645])")
INT_NUM = re.compile(r"\d+")
FEE_LINE = re.compile(r"FEE\s*[:=]\s*([0-9][0-9,\u066C\u2009\u202F ]*)", re.IGNORECASE)
SELL_HEADER = re.compile(r"^(?:فروش|sell)\s*:?\s*$", re.IGNORECASE)
BUY_HEADER = re.compile(r"^(?:خرید|buy)\s*:?\s*$", re.IGNORECASE)

REASON_MESSAGES = {
    "empty": "خط خالی است.",
    "amount_not_found": "مقدار با پسوند m/م پیدا نشد.",
    "amount_not_decimal": "مقدار عددی معتبر نیست.",
    "rate_not_found_or_out_of_range": "نرخ فی ۵ یا ۶ رقمی در بازه 10000 تا 200000 پیدا نشد.",
    "name_invalid": "اسم فرد بین مقدار و نرخ پیدا نشد.",
    "row_sanity_failed": "سنیتی‌چک بازسازی مبلغ از مقدار و نرخ رد شد.",
}


class UserInputError(ValueError):
    """خطای قابل نمایش به کاربر."""


@dataclass(frozen=True)
class ParsedEntry:
    section: str
    raw_line: str
    line_number: int
    name: str
    amount: Decimal
    amount_k: Decimal
    rate: Decimal


@dataclass(frozen=True)
class RejectedLine:
    section: str
    raw_line: str
    reason_code: str
    reason_text: str


@dataclass(frozen=True)
class StageTwoRow:
    section: str
    name: str
    amount: Decimal
    rate: Decimal
    actual_amount: Decimal
    day_amount: Decimal
    difference: Decimal
    simple_difference: Decimal
    status: str


@dataclass(frozen=True)
class CalculationResult:
    raw_message: str
    normalized_message: str
    report_date: str | None
    rate_day: Decimal | None
    entries: list[ParsedEntry]
    rejected_lines: list[RejectedLine]
    sum_sell: Decimal
    sum_buy: Decimal
    net_total: Decimal
    stage_two_rows: list[StageTwoRow]
    sum_deb_sell: Decimal
    sum_cred_sell: Decimal
    sum_deb_buy: Decimal
    sum_cred_buy: Decimal
    halted: bool
    halt_reason: str | None
    needs_rate_day: bool


def to_latin_digits(value: str) -> str:
    return value.translate(PERSIAN_DIGITS).translate(ARABIC_DIGITS)


def normalize_text(value: str) -> str:
    normalized = to_latin_digits(value).replace("\r\n", "\n").replace("\r", "\n")
    normalized = CTRL_WS_PATTERN.sub(" ", normalized)

    lines: list[str] = []
    for line in normalized.split("\n"):
        lines.append(SPACE_PATTERN.sub(" ", line).strip())

    return "\n".join(lines)


def clean_number_string(value: str) -> str:
    return re.sub(r"[, \u066C\u2009\u202F]", "", value)


def collapse_numeric_separators(value: str) -> str:
    return THOUSANDS_SEPARATOR_PATTERN.sub("", value)


def sanitize_name(value: str) -> str:
    value = value.strip(" |:.-_/\\")
    return SPACE_PATTERN.sub(" ", value).strip()


def parse_fee(raw_message: str) -> Decimal | None:
    normalized = collapse_numeric_separators(to_latin_digits(raw_message))
    match = FEE_LINE.search(normalized)
    if not match:
        return None

    rate_text = clean_number_string(match.group(1))
    if not rate_text:
        return None
    return Decimal(rate_text)


def extract_report_date(raw_message: str) -> str | None:
    for raw_line in raw_message.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        normalized = normalize_text(stripped)
        if detect_section(normalized):
            return None
        if FEE_LINE.search(collapse_numeric_separators(normalized)):
            return None
        return normalized

    return None


def detect_section(line: str) -> str | None:
    normalized = normalize_text(line)
    if SELL_HEADER.fullmatch(normalized):
        return "فروش"
    if BUY_HEADER.fullmatch(normalized):
        return "خرید"
    return None


def split_sections(lines: list[str]) -> list[tuple[str, int, str]]:
    section: str | None = None
    items: list[tuple[str, int, str]] = []

    for line_number, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue

        normalized = normalize_text(stripped)
        if FEE_LINE.search(collapse_numeric_separators(normalized)):
            continue

        section_match = detect_section(normalized)
        if section_match:
            section = section_match
            continue

        if section not in ("فروش", "خرید"):
            continue

        items.append((section, line_number, raw_line))

    return items


def standardize_trade_line(raw_line: str) -> str:
    cleaned = to_latin_digits(raw_line)
    cleaned = CTRL_WS_PATTERN.sub(" ", cleaned)
    cleaned = (
        cleaned.replace("|", " ")
        .replace(":", " ")
        .replace("-", " ")
        .replace("—", " ")
        .replace("–", " ")
    )
    cleaned = collapse_numeric_separators(cleaned)
    return SPACE_PATTERN.sub(" ", cleaned).strip()


def parse_amount_token(token: str) -> Decimal:
    amount_text = token.replace("٫", ".")
    if "," in amount_text and "." not in amount_text:
        head, _, tail = amount_text.partition(",")
        if tail and len(tail) != 3:
            amount_text = f"{head}.{tail}"
        else:
            amount_text = amount_text.replace(",", "")
    else:
        amount_text = amount_text.replace(",", "")

    return Decimal(amount_text)


def parse_line(raw_line: str) -> tuple[Decimal | None, str | None, Decimal | None, str | None]:
    stripped = raw_line.strip()
    if not stripped:
        return None, None, None, "empty"

    cleaned = standardize_trade_line(stripped)
    amount_match = AMOUNT_TOKEN.search(cleaned)
    if not amount_match:
        return None, None, None, "amount_not_found"

    try:
        amount = parse_amount_token(amount_match.group("val"))
    except Exception:
        return None, None, None, "amount_not_decimal"

    amount_k = amount * THOUSAND

    rate = find_rate(cleaned)
    if rate is None:
        return None, None, None, "rate_not_found_or_out_of_range"

    rate_text = str(int(rate))
    rate_pos = cleaned.rfind(rate_text)
    name = sanitize_name(cleaned[amount_match.end() : rate_pos])
    if not name or name.isdigit():
        return None, None, None, "name_invalid"

    return amount_k, name, rate, None


def find_rate(cleaned_line: str) -> Decimal | None:
    rate: Decimal | None = None
    for token in reversed(INT_NUM.findall(cleaned_line)):
        if len(token) not in (5, 6):
            continue

        numeric = int(token)
        if RATE_MIN <= numeric <= RATE_MAX:
            rate = Decimal(token)
            break

    return rate


def run_sanity_checks() -> None:
    sample = Decimal(10000) / Decimal(92280)
    if format_decimal(sample) != "0.10836584":
        raise RuntimeError("Sanity check failed: 10000/92280 != 0.10836584")


def analyze_message(raw_message: str) -> CalculationResult:
    if not raw_message or not raw_message.strip():
        raise UserInputError("پیام خالی است. لیست خرید و فروش را ارسال کنید.")

    run_sanity_checks()

    normalized_message = normalize_text(raw_message)
    report_date = extract_report_date(raw_message)
    rate_day = parse_fee(raw_message)
    items = split_sections(raw_message.splitlines())

    entries: list[ParsedEntry] = []
    rejected_lines: list[RejectedLine] = []

    for section, line_number, raw_line in items:
        amount_k, name, rate, reason = parse_line(raw_line)
        if reason is not None:
            rejected_lines.append(
                RejectedLine(
                    section=section,
                    raw_line=raw_line.strip(),
                    reason_code=reason,
                    reason_text=reason_message(reason),
                )
            )
            continue

        entries.append(
            ParsedEntry(
                section=section,
                raw_line=raw_line.strip(),
                line_number=line_number,
                name=name or "",
                amount=(amount_k or Decimal("0")) / THOUSAND,
                amount_k=amount_k or Decimal("0"),
                rate=rate or Decimal("0"),
            )
        )

    if not entries:
        raise UserInputError(
            "هیچ ردیف معتبری پیدا نشد. هر ردیف باید مقدار با m/م، اسم فرد و نرخ فی معتبر داشته باشد."
        )

    sum_sell = Decimal("0")
    sum_buy = Decimal("0")

    for entry in entries:
        actual = entry.amount_k / entry.rate
        rebuild_delta = abs((actual * entry.rate) - entry.amount_k)
        if rebuild_delta > Decimal("0.5"):
            rejected_lines.append(
                RejectedLine(
                    section=entry.section,
                    raw_line=entry.raw_line,
                    reason_code="row_sanity_failed",
                    reason_text=reason_message("row_sanity_failed"),
                )
            )

        if entry.section == "فروش":
            sum_sell += actual
        else:
            sum_buy += actual

    halted = False
    halt_reason: str | None = None
    if sum_sell > ABNORMAL_TOTAL_LIMIT or sum_buy > ABNORMAL_TOTAL_LIMIT:
        halted = True
        halt_reason = (
            "مجموع فروش واقعی یا خرید واقعی از حد سنیتی‌چک مجاز بیشتر شد. "
            "برای این سبک داده، مقدارهای بالاتر از 5 غیرعادی فرض شده‌اند."
        )

    stage_two_rows: list[StageTwoRow] = []
    sum_deb_sell = Decimal("0")
    sum_cred_sell = Decimal("0")
    sum_deb_buy = Decimal("0")
    sum_cred_buy = Decimal("0")

    if rate_day is not None and not halted:
        if rate_day <= 0:
            raise UserInputError("FEE باید بزرگ‌تر از صفر باشد.")

        for entry in entries:
            actual = entry.amount_k / entry.rate
            day_amount = entry.amount_k / rate_day
            difference = actual - day_amount if entry.section == "فروش" else day_amount - actual
            simple_difference = difference * MILLION
            status = determine_status(difference)

            stage_two_rows.append(
                StageTwoRow(
                    section=entry.section,
                    name=entry.name,
                    amount=entry.amount,
                    rate=entry.rate,
                    actual_amount=actual,
                    day_amount=day_amount,
                    difference=difference,
                    simple_difference=simple_difference,
                    status=status,
                )
            )

            if entry.section == "فروش":
                if difference > 0:
                    sum_deb_sell += difference
                elif difference < 0:
                    sum_cred_sell += difference
            else:
                if difference > 0:
                    sum_deb_buy += difference
                elif difference < 0:
                    sum_cred_buy += difference

    return CalculationResult(
        raw_message=raw_message,
        normalized_message=normalized_message,
        report_date=report_date,
        rate_day=rate_day,
        entries=entries,
        rejected_lines=rejected_lines,
        sum_sell=sum_sell,
        sum_buy=sum_buy,
        net_total=sum_sell - sum_buy,
        stage_two_rows=stage_two_rows,
        sum_deb_sell=sum_deb_sell,
        sum_cred_sell=sum_cred_sell,
        sum_deb_buy=sum_deb_buy,
        sum_cred_buy=sum_cred_buy,
        halted=halted,
        halt_reason=halt_reason,
        needs_rate_day=(rate_day is None and not halted),
    )


def reason_message(reason_code: str) -> str:
    return REASON_MESSAGES.get(reason_code, "خطای نامشخص در پردازش ردیف.")


def determine_status(difference: Decimal) -> str:
    if difference > 0:
        return "می‌گیرم"
    if difference < 0:
        return "می‌دهم"
    return "خنثی"


def format_decimal(value: Decimal) -> str:
    return f"{value.quantize(DISPLAY_QUANT, rounding=ROUND_HALF_EVEN):f}"


def render_result(result: CalculationResult) -> str:
    net_label = summarize_net_label(result.net_total)
    parts: list[str] = [
        "مرحله اول (بدون نرخ روز)",
        f"{net_label}: {format_decimal(result.net_total)}",
    ]

    if result.rejected_lines:
        parts.append("")
        parts.append("ردیف‌های ردشده/مشکوک:")
        for issue in result.rejected_lines:
            line_text = issue.raw_line if issue.raw_line else "(بدون متن)"
            parts.append(
                f"- [{issue.section}] {line_text} -> {issue.reason_code}: {issue.reason_text}"
            )

    if result.halted:
        parts.append("")
        parts.append(f"هشدار سنیتی‌چک: {result.halt_reason}")
        parts.append("پردازش در همین مرحله متوقف شد.")
        return "\n".join(parts)

    if result.rate_day is None:
        parts.append("")
        parts.append("FEE پیدا نشد. FEE را می‌دهی تا جدول کامل را بسازم؟")
        return "\n".join(parts)

    parts.append("")
    parts.append(f"FEE: {format_decimal(result.rate_day)}")
    parts.append("")
    parts.append("جدول کامل (با FEE):")
    parts.append(render_stage_two_table(result.stage_two_rows))
    parts.append("")
    parts.append("جدول تفکیکی وضعیت‌ها:")
    parts.append(render_grouped_stage_two_table(result.stage_two_rows))

    return "\n".join(parts)


def render_stage_two_table(rows: list[StageTwoRow]) -> str:
    headers = [
        "اسم فرد",
        "ساده‌شده",
        "مقدار",
        "نرخ",
        "خرید یا فروش",
        "وضعیت",
    ]
    values = [
        [
            row.name,
            format_decimal(row.simple_difference),
            format_amount(row.amount),
            format_rate(row.rate),
            row.section,
            row.status,
        ]
        for row in rows
    ]

    widths = compute_widths(headers, values)
    separator = "-+-".join("-" * width for width in widths)

    rendered = [format_row(headers, widths), separator]
    rendered.extend(format_row(row, widths) for row in values)
    return "```\n" + "\n".join(rendered) + "\n```"


def compute_widths(headers: list[str], rows: list[list[str]]) -> list[int]:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))
    return widths


def format_row(values: Iterable[str], widths: list[int]) -> str:
    rendered: list[str] = []
    for index, value in enumerate(values):
        if index in (1, 2, 3):
            rendered.append(value.rjust(widths[index]))
        else:
            rendered.append(value.ljust(widths[index]))
    return " | ".join(rendered)


def render_grouped_stage_two_table(rows: list[StageTwoRow]) -> str:
    grouped_rows: list[StageTwoRow] = []
    for status in ("می‌گیرم", "می‌دهم", "خنثی"):
        grouped_rows.extend(row for row in rows if row.status == status)
    return render_stage_two_table(grouped_rows)


def summarize_net_label(net_total: Decimal) -> str:
    if net_total > 0:
        return "سود کلی"
    if net_total < 0:
        return "ضرر کلی"
    return "نتیجه کلی"


def format_amount(value: Decimal) -> str:
    return f"{strip_trailing_zeros(value)}م"


def format_rate(value: Decimal) -> str:
    return strip_trailing_zeros(value)


def strip_trailing_zeros(value: Decimal) -> str:
    rendered = f"{value:f}"
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def extract_fee_only(message_text: str) -> Decimal | None:
    normalized = normalize_text(message_text)
    if "\n" in normalized:
        return None

    match = FEE_LINE.fullmatch(collapse_numeric_separators(normalized))
    if not match:
        return None

    return Decimal(clean_number_string(match.group(1)))
