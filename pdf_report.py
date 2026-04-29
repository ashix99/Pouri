from __future__ import annotations

from pathlib import Path
import os
import tempfile
import urllib.request
import uuid

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from fx_calculator import (
    CalculationResult,
    StageTwoRow,
    format_amount,
    format_decimal,
    format_rate,
    summarize_net_label,
)

FONT_NAME = "PouriReportFont"
FONT_NAME_BOLD = "PouriReportFontBold"
PROJECT_ROOT = Path(__file__).resolve().parent
FONTS_DIR = PROJECT_ROOT / "fonts"
DOWNLOADED_REGULAR_FONT = FONTS_DIR / "Vazirmatn-Regular.ttf"
DOWNLOADED_BOLD_FONT = FONTS_DIR / "Vazirmatn-Bold.ttf"
DOWNLOADED_REGULAR_URL = "https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/fonts/ttf/Vazirmatn-Regular.ttf"
DOWNLOADED_BOLD_URL = "https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/fonts/ttf/Vazirmatn-Bold.ttf"
FONT_CANDIDATES = (
    lambda: os.getenv("PDF_FONT_PATH", "").strip(),
    lambda: str(PROJECT_ROOT / "fonts" / "YekanBakh-Regular.ttf"),
    lambda: str(PROJECT_ROOT / "fonts" / "YekanBakhFaNum-Regular.ttf"),
    lambda: str(DOWNLOADED_REGULAR_FONT),
    lambda: r"C:\Windows\Fonts\tahoma.ttf",
    lambda: r"C:\Windows\Fonts\arial.ttf",
    lambda: "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    lambda: "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    lambda: "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    lambda: "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
)
FONT_BOLD_CANDIDATES = (
    lambda: os.getenv("PDF_FONT_BOLD_PATH", "").strip(),
    lambda: str(PROJECT_ROOT / "fonts" / "YekanBakh-Bold.ttf"),
    lambda: str(PROJECT_ROOT / "fonts" / "YekanBakhFaNum-Bold.ttf"),
    lambda: str(DOWNLOADED_BOLD_FONT),
    lambda: r"C:\Windows\Fonts\tahomabd.ttf",
    lambda: r"C:\Windows\Fonts\arialbd.ttf",
    lambda: "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    lambda: "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
    lambda: "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
)


def build_report_pdf(result: CalculationResult) -> str:
    register_fonts()

    output_path = Path(tempfile.gettempdir()) / f"pouri-report-{uuid.uuid4().hex}.pdf"
    page_width, _ = landscape(A4)
    page_height = estimate_page_height(result)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=(page_width, page_height),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    styles = build_styles()
    story = [
        Paragraph(shape_text("گزارش معاملات ارزی پوری"), styles["title"]),
    ]

    if result.report_date:
        story.extend(
            [
                Spacer(1, 2 * mm),
                Paragraph(shape_text(result.report_date), styles["subtitle"]),
            ]
        )

    story.extend(
        [
        Spacer(1, 6 * mm),
        Paragraph(shape_text("خلاصه مرحله اول"), styles["section"]),
        Spacer(1, 2 * mm),
        build_stage_one_table(result, styles),
        ]
    )

    if result.rate_day is not None:
        story.extend(
            [
                Spacer(1, 4 * mm),
                Paragraph(
                    shape_text(f"FEE: {format_decimal(result.rate_day)}"),
                    styles["body"],
                ),
            ]
        )
    else:
        story.extend(
            [
                Spacer(1, 4 * mm),
                Paragraph(
                    shape_text("FEE در پیام نبود و جدول کامل هنوز ساخته نشده است."),
                    styles["body"],
                ),
            ]
        )

    if result.rejected_lines:
        story.extend(
            [
                Spacer(1, 5 * mm),
                Paragraph(shape_text("ردیف‌های ردشده یا مشکوک"), styles["section"]),
                Spacer(1, 2 * mm),
                build_rejected_table(result, styles),
            ]
        )

    if result.halted:
        story.extend(
            [
                Spacer(1, 5 * mm),
                Paragraph(shape_text("هشدار سنیتی‌چک"), styles["section"]),
                Spacer(1, 2 * mm),
                Paragraph(shape_text(result.halt_reason or ""), styles["warning"]),
            ]
        )
    elif result.stage_two_rows:
        story.extend(
            [
                Spacer(1, 5 * mm),
                Paragraph(shape_text("جدول کامل با FEE"), styles["section"]),
                Spacer(1, 2 * mm),
                build_stage_two_table(result.stage_two_rows, styles),
                Spacer(1, 4 * mm),
                Paragraph(shape_text("جدول تفکیکی وضعیت‌ها"), styles["section"]),
                Spacer(1, 2 * mm),
                build_grouped_stage_two_table(result.stage_two_rows, styles),
            ]
        )

    doc.build(story)
    return str(output_path)


def register_fonts() -> None:
    regular_font = resolve_font_path(FONT_CANDIDATES)
    bold_font = resolve_font_path(FONT_BOLD_CANDIDATES)

    if regular_font is None:
        regular_font = download_font_if_needed(DOWNLOADED_REGULAR_FONT, DOWNLOADED_REGULAR_URL)
    if bold_font is None:
        bold_font = download_font_if_needed(DOWNLOADED_BOLD_FONT, DOWNLOADED_BOLD_URL)

    if regular_font and FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME, regular_font))
    if bold_font and FONT_NAME_BOLD not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, bold_font))


def resolve_font_path(candidates: tuple) -> str | None:
    for factory in candidates:
        path = factory()
        if path and Path(path).exists():
            return path
    return None


def download_font_if_needed(target_path: Path, url: str) -> str | None:
    try:
        if target_path.exists():
            return str(target_path)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.with_suffix(target_path.suffix + ".tmp")

        with urllib.request.urlopen(url, timeout=30) as response:
            temp_path.write_bytes(response.read())

        temp_path.replace(target_path)
        return str(target_path)
    except Exception:
        return None


def build_styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    regular_font_name = FONT_NAME if FONT_NAME in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    bold_font_name = FONT_NAME_BOLD if FONT_NAME_BOLD in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    return {
        "title": ParagraphStyle(
            "PouriTitle",
            parent=sample["Heading1"],
            fontName=bold_font_name,
            fontSize=16,
            leading=20,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#17324D"),
        ),
        "section": ParagraphStyle(
            "PouriSection",
            parent=sample["Heading2"],
            fontName=bold_font_name,
            fontSize=11,
            leading=14,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#284E73"),
        ),
        "subtitle": ParagraphStyle(
            "PouriSubtitle",
            parent=sample["BodyText"],
            fontName=bold_font_name,
            fontSize=10,
            leading=13,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#506D86"),
        ),
        "body": ParagraphStyle(
            "PouriBody",
            parent=sample["BodyText"],
            fontName=regular_font_name,
            fontSize=9,
            leading=12,
            alignment=TA_RIGHT,
        ),
        "cell_rtl": ParagraphStyle(
            "PouriCellRtl",
            parent=sample["BodyText"],
            fontName=regular_font_name,
            fontSize=8.5,
            leading=10.5,
            alignment=TA_RIGHT,
        ),
        "cell_center": ParagraphStyle(
            "PouriCellCenter",
            parent=sample["BodyText"],
            fontName=regular_font_name,
            fontSize=8.5,
            leading=10.5,
            alignment=TA_CENTER,
        ),
        "warning": ParagraphStyle(
            "PouriWarning",
            parent=sample["BodyText"],
            fontName=regular_font_name,
            fontSize=9,
            leading=12,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#8A3B12"),
        ),
    }


def build_stage_one_table(result: CalculationResult, styles: dict[str, ParagraphStyle]) -> Table:
    net_label = summarize_net_label(result.net_total)
    data = [
        [rtl_cell("شاخص", styles), rtl_cell("مقدار", styles)],
        [rtl_cell(net_label, styles), center_cell(format_decimal(result.net_total), styles)],
    ]
    table = Table(data, colWidths=[110 * mm, 65 * mm], hAlign="RIGHT")
    table.setStyle(build_grid_style(header_fill="#DDEAF7"))
    return table


def build_rejected_table(result: CalculationResult, styles: dict[str, ParagraphStyle]) -> Table:
    data = [
        [
            rtl_cell("بخش", styles),
            rtl_cell("ردیف", styles),
            rtl_cell("کد دلیل", styles),
            rtl_cell("توضیح", styles),
        ]
    ]
    for item in result.rejected_lines:
        data.append(
            [
                rtl_cell(item.section, styles),
                rtl_cell(item.raw_line, styles),
                center_cell(item.reason_code, styles),
                rtl_cell(item.reason_text, styles),
            ]
        )

    table = Table(
        data,
        colWidths=[24 * mm, 90 * mm, 42 * mm, 85 * mm],
        repeatRows=1,
        hAlign="RIGHT",
    )
    table.setStyle(build_grid_style(header_fill="#FCE5DB"))
    return table


def build_stage_two_table(rows: list[StageTwoRow], styles: dict[str, ParagraphStyle]) -> Table:
    data = [
        [
            rtl_cell("وضعیت", styles),
            rtl_cell("خرید یا فروش", styles),
            rtl_cell("نرخ", styles),
            rtl_cell("مقدار", styles),
            rtl_cell("ساده شده", styles),
            rtl_cell("اسم", styles),
        ]
    ]
    for row in rows:
        data.append(
            [
                rtl_cell(row.status, styles),
                rtl_cell(row.section, styles),
                center_cell(format_rate(row.rate), styles),
                center_cell(format_amount(row.amount), styles),
                center_cell(format_decimal(row.simple_difference), styles),
                rtl_cell(row.name, styles),
            ]
        )

    table = Table(
        data,
        colWidths=[24 * mm, 28 * mm, 26 * mm, 24 * mm, 34 * mm, 54 * mm],
        repeatRows=1,
        hAlign="RIGHT",
    )
    table.setStyle(build_grid_style(header_fill="#DFF1E3"))
    return table


def build_grouped_stage_two_table(rows: list[StageTwoRow], styles: dict[str, ParagraphStyle]) -> Table:
    ordered_rows: list[StageTwoRow] = []
    for status in ("می‌گیرم", "می‌دهم", "خنثی"):
        ordered_rows.extend(row for row in rows if row.status == status)
    return build_stage_two_table(ordered_rows, styles)


def build_grid_style(header_fill: str) -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_fill)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#17324D")),
            ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#8FA5B8")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#6F879B")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]
    )


def rtl_cell(text: str, styles: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(shape_text(text), styles["cell_rtl"])


def center_cell(text: str, styles: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(shape_text(text), styles["cell_center"])


def shape_text(text: str) -> str:
    if not text:
        return ""
    if not contains_rtl(text):
        return text
    return get_display(arabic_reshaper.reshape(text))


def contains_rtl(text: str) -> bool:
    return any("\u0600" <= char <= "\u06FF" for char in text)


def estimate_page_height(result: CalculationResult) -> float:
    base_height = 150 * mm
    row_height = 9 * mm
    stage_one_rows = 2
    rejected_rows = len(result.rejected_lines) + 1 if result.rejected_lines else 0
    stage_two_rows = len(result.stage_two_rows) + 1 if result.stage_two_rows else 0
    grouped_rows = len(result.stage_two_rows) + 1 if result.stage_two_rows else 0
    date_extra = 10 * mm if result.report_date else 0
    total_height = (
        base_height
        + date_extra
        + (stage_one_rows * row_height)
        + (rejected_rows * row_height)
        + (stage_two_rows * row_height)
        + (grouped_rows * row_height)
    )
    return max(landscape(A4)[1], total_height)
