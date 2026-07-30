"""Check the V33 Song sample shifted 50 mm upward."""

from __future__ import annotations

import check_paper_a4_zhang_jia_le_v32 as shared
import generate_paper_a4_zhang_jia_le_v33 as variant


def main() -> None:
    shared.variant = variant
    shared.CHECK_VARIANT = "V33"
    shared.main()


if __name__ == "__main__":
    main()
