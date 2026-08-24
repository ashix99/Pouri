from decimal import Decimal
import unittest

from fx_calculator import (
    analyze_message,
    extract_fee_only,
    extract_report_date,
    format_decimal,
    normalize_text,
    parse_line,
    parse_fee,
    render_result,
)


class FxCalculatorTests(unittest.TestCase):
    def test_normalize_text_converts_digits_and_keeps_lines(self) -> None:
        raw = "فروش\n۶م علی ۱۵۳٬۲۰۰\nFEE: ۱۵۲٬۶۰۰"
        normalized = normalize_text(raw)

        self.assertIn("6م", normalized)
        self.assertIn("153٬200", normalized)
        self.assertIn("152٬600", normalized)

    def test_parse_fee_handles_separators(self) -> None:
        rate_day = parse_fee("FEE: 152,600")
        self.assertEqual(rate_day, Decimal("152600"))

    def test_parse_line_extracts_amount_name_and_rate(self) -> None:
        amount_k, name, rate, reason = parse_line("2.5m رضا | 149950")

        self.assertIsNone(reason)
        self.assertEqual(amount_k, Decimal("2500"))
        self.assertEqual(name, "رضا")
        self.assertEqual(rate, Decimal("149950"))

    def test_parse_line_accepts_six_digit_rate_above_old_limit(self) -> None:
        amount_k, name, rate, reason = parse_line("۱م نرخ تسویه ۲۰۰۹۵۰")

        self.assertIsNone(reason)
        self.assertEqual(amount_k, Decimal("1000"))
        self.assertEqual(name, "نرخ تسویه")
        self.assertEqual(rate, Decimal("200950"))

    def test_parse_line_rejects_rate_longer_than_six_digits(self) -> None:
        amount_k, name, rate, reason = parse_line("1m رضا 1000000")

        self.assertIsNone(amount_k)
        self.assertIsNone(name)
        self.assertIsNone(rate)
        self.assertEqual(reason, "rate_not_found_or_out_of_range")

    def test_extract_report_date_uses_first_non_empty_line_before_sections(self) -> None:
        date_line = extract_report_date("دوشنبه ۷ برج\n\nفروش\n6m علی 153200")
        self.assertEqual(date_line, "دوشنبه 7 برج")

    def test_analyze_message_without_rate_day_requests_followup(self) -> None:
        text = """
        فروش
        6m علی 153200
        2m رضا 150000

        خرید
        4m سارا 151800
        """
        result = analyze_message(text)
        rendered = render_result(result)

        self.assertTrue(result.needs_rate_day)
        self.assertIsNone(result.rate_day)
        self.assertIn("مرحله اول", rendered)
        self.assertIn("FEE را می‌دهی", rendered)
        self.assertNotIn("مجموع مقدار فروش واقعی", rendered)

    def test_analyze_message_with_rate_day_builds_stage_two(self) -> None:
        text = """
        دوشنبه ۷ برج

        فروش
        6m علی 153200
        2m رضا 150000

        خرید
        4m سارا 151800

        FEE: 152600
        """
        result = analyze_message(text)
        rendered = render_result(result)

        self.assertEqual(result.rate_day, Decimal("152600"))
        self.assertEqual(result.report_date, "دوشنبه 7 برج")
        self.assertEqual(len(result.stage_two_rows), 3)
        self.assertIn("جدول کامل", rendered)
        self.assertIn("جدول تفکیکی وضعیت‌ها", rendered)
        self.assertIn("می‌گیرم", rendered)

    def test_analyze_message_stops_on_abnormal_total(self) -> None:
        text = """
        فروش
        900m علی 10000

        خرید
        1m رضا 10000
        """
        result = analyze_message(text)
        rendered = render_result(result)

        self.assertTrue(result.halted)
        self.assertIn("پردازش در همین مرحله متوقف شد", rendered)

    def test_extract_fee_only(self) -> None:
        rate_day = extract_fee_only("FEE: 152600")
        self.assertEqual(rate_day, Decimal("152600"))

    def test_format_decimal_is_fixed_point(self) -> None:
        self.assertEqual(format_decimal(Decimal("1") / Decimal("8")), "0.12500000")


if __name__ == "__main__":
    unittest.main()
