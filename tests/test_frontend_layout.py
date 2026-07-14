import re
import unittest
from pathlib import Path


CSS_PATH = Path(__file__).resolve().parents[1] / "host" / "static" / "style.css"


class FrontendLayoutCssTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = CSS_PATH.read_text(encoding="utf-8")

    def _media_block(self, max_width):
        marker = f"@media (max-width: {max_width}px)"
        start = self.css.index(marker)
        opening = self.css.index("{", start)
        depth = 1
        for index in range(opening + 1, len(self.css)):
            if self.css[index] == "{":
                depth += 1
            elif self.css[index] == "}":
                depth -= 1
                if depth == 0:
                    return self.css[opening + 1:index]
        self.fail(f"unterminated media block: {marker}")

    def _rule(self, css, selector):
        match = re.search(
            rf"(?ms)^\s*{re.escape(selector)}\s*\{{([^}}]*)\}}",
            css,
        )
        self.assertIsNotNone(match, f"missing {selector} rule")
        return match.group(1)

    def test_responsive_chart_panel_has_definite_height(self):
        desktop = self._rule(self._media_block(1180), ".chart-panel")
        mobile = self._rule(self._media_block(720), ".chart-panel")

        self.assertRegex(desktop, r"(?m)^\s*height:\s*520px;")
        self.assertRegex(mobile, r"(?m)^\s*height:\s*780px;")

    def test_mobile_chart_grid_allocates_one_row_per_chart(self):
        chart_grid = self._rule(self._media_block(720), ".chart-grid")

        self.assertRegex(
            chart_grid,
            r"grid-template-rows:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\);",
        )


if __name__ == "__main__":
    unittest.main()
