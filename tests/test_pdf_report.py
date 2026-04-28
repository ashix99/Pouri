from pathlib import Path
import unittest

from fx_calculator import analyze_message
from pdf_report import build_report_pdf


class PdfReportTests(unittest.TestCase):
    def test_build_report_pdf_creates_non_empty_file(self) -> None:
        sample = """
        دوشنبه ۷ برج

        sell
        6m Ali 153200
        2.5m Reza 149950

        buy
        4m Sara 151800
        1.75m Mehdi 150400

        RATE_DAY: 152600
        """
        result = analyze_message(sample)
        pdf_path = build_report_pdf(result)
        path = Path(pdf_path)

        try:
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 0)
        finally:
            if path.exists():
                path.unlink()


if __name__ == "__main__":
    unittest.main()
