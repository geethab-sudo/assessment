#!/usr/bin/env python3
"""Preview certificate field placement (name, date, signature overlay).

Usage:
  python3 scripts/preview_certificate.py --name "Jane Doe" --level beginner
  python3 scripts/preview_certificate.py --template Begineer.jpg --name "Test User"
  python3 scripts/preview_certificate.py --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.certificate_service import (  # noqa: E402
    list_certificate_templates,
    render_certificate,
    render_certificate_template,
    template_filename_for_level,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview certificate rendering")
    parser.add_argument("--name", default="Preview Student", help="Name on certificate")
    parser.add_argument(
        "--level",
        choices=("beginner", "intermediate", "advanced"),
        default="beginner",
    )
    parser.add_argument("--template", help="Template filename (overrides --level)")
    parser.add_argument("--list", action="store_true", help="List templates and calibration status")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_ROOT / "certificates" / "previews",
        help="Directory for preview JPEGs",
    )
    args = parser.parse_args()

    if args.list:
        for t in list_certificate_templates():
            status = "OK" if t.calibrated else "NEEDS SETUP"
            levels = ", ".join(t.levels) if t.levels else "—"
            print(f"{t.filename:24}  {status:12}  levels: {levels}")
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.template:
        result = render_certificate_template(args.template, args.name)
        out = args.output_dir / f"preview-{Path(args.template).stem}.jpg"
    else:
        tpl = template_filename_for_level(args.level)
        result = render_certificate_template(tpl, args.name)
        out = args.output_dir / f"preview-{args.level}.jpg"

    out.write_bytes(result.image_bytes)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
