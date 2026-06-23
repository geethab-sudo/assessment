"""
Render Tier 1 completion certificates by overlaying dynamic fields on JPG templates.

Layout is stored in ``certificates/layout.json`` keyed by **template filename**.
Use the admin **Certificate layout** page to click-calibrate name, date, and signature
positions per template. Uncalibrated templates cannot be issued.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw, ImageFont

from services import db_service

CERTIFICATE_LEVEL = Literal["beginner", "intermediate", "advanced"]
CERTIFICATE_THRESHOLD = 0.85

_CERTS_DIR = Path(__file__).resolve().parent.parent / "certificates"
_LAYOUT_PATH = _CERTS_DIR / "layout.json"
_TEMPLATE_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]+\.(?:jpg|jpeg|png)$", re.I)

_NAME_FONT_CANDIDATES = (
    _CERTS_DIR / "fonts" / "GreatVibes-Regular.ttf",
    _CERTS_DIR / "fonts" / "DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-RI.ttf",
)
_DATE_FONT_CANDIDATES = (
    _CERTS_DIR / "fonts" / "DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
)

_layout_cache: dict[str, Any] | None = None
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


@dataclass(frozen=True)
class CertificateRenderResult:
    image_bytes: bytes
    media_type: str
    filename: str


@dataclass(frozen=True)
class CertificateTemplateInfo:
    filename: str
    width: int
    height: int
    calibrated: bool
    levels: list[str]
    layout: dict[str, Any] | None


def certificates_dir() -> Path:
    return _CERTS_DIR


def invalidate_layout_cache() -> None:
    global _layout_cache
    _layout_cache = None


def _migrate_levels_to_templates(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert legacy ``levels`` block to ``templates`` + ``level_template``."""
    if raw.get("templates"):
        return raw
    templates: dict[str, Any] = dict(raw.get("templates") or {})
    level_template: dict[str, str] = dict(raw.get("level_template") or {})
    for lv, cfg in (raw.get("levels") or {}).items():
        if not isinstance(cfg, dict):
            continue
        tpl = str(cfg.get("template") or "").strip()
        if not tpl:
            continue
        level_template[str(lv).strip().lower()] = tpl
        templates[tpl] = {
            "display_name": cfg.get("display_name") or {},
            "issue_date": cfg.get("issue_date") or {},
            "signature": cfg.get("signature") or {},
        }
    raw["templates"] = templates
    raw["level_template"] = level_template
    raw.pop("levels", None)
    return raw


def load_layout(*, reload: bool = False) -> dict[str, Any]:
    global _layout_cache
    if reload or _layout_cache is None:
        with _LAYOUT_PATH.open(encoding="utf-8") as fh:
            raw = json.load(fh)
        _layout_cache = _migrate_levels_to_templates(raw)
    return _layout_cache


def save_layout(layout: dict[str, Any]) -> None:
    """Persist layout JSON and refresh cache."""
    layout = _migrate_levels_to_templates(layout)
    with _LAYOUT_PATH.open("w", encoding="utf-8") as fh:
        json.dump(layout, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    invalidate_layout_cache()
    load_layout()


def _excluded_template_names(layout: dict[str, Any]) -> set[str]:
    excluded = set(layout.get("excluded_templates") or [])
    excluded.add("layout.json")
    return {str(x).strip() for x in excluded if str(x).strip()}


def validate_template_filename(filename: str) -> str:
    name = (filename or "").strip()
    if not name or not _SAFE_FILENAME.match(name):
        raise ValueError("Invalid certificate template filename.")
    path = (_CERTS_DIR / name).resolve()
    if not str(path).startswith(str(_CERTS_DIR.resolve())):
        raise ValueError("Invalid certificate template path.")
    if not path.is_file():
        raise FileNotFoundError(f"Certificate template not found: {name}")
    return name


def discover_template_filenames() -> list[str]:
    layout = load_layout()
    excluded = _excluded_template_names(layout)
    excluded.update({"signature.png", "signature.jpg", "signature.jpeg"})
    names: list[str] = []
    for path in sorted(_CERTS_DIR.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _TEMPLATE_IMAGE_SUFFIXES:
            continue
        if path.name in excluded:
            continue
        if path.parent.name == "previews":
            continue
        names.append(path.name)
    return names


def _levels_for_template(layout: dict[str, Any], filename: str) -> list[str]:
    level_template = layout.get("level_template") or {}
    return sorted(
        lv
        for lv, tpl in level_template.items()
        if str(tpl).strip() == filename
    )


def _field_is_complete(field: dict[str, Any] | None, *, kind: str) -> bool:
    if not isinstance(field, dict):
        return False
    if "x_ratio" not in field or "y_ratio" not in field:
        return False
    if kind == "signature":
        return "max_width_ratio" in field and "max_height_ratio" in field
    return "size" in field and str(field.get("color", "")).strip() != ""


def is_template_calibrated(filename: str, layout: dict[str, Any] | None = None) -> bool:
    layout = layout or load_layout()
    tpl = (layout.get("templates") or {}).get(filename)
    if not isinstance(tpl, dict):
        return False
    return (
        _field_is_complete(tpl.get("display_name"), kind="text")
        and _field_is_complete(tpl.get("issue_date"), kind="text")
        and _field_is_complete(tpl.get("signature"), kind="signature")
    )


def list_certificate_templates() -> list[CertificateTemplateInfo]:
    layout = load_layout()
    out: list[CertificateTemplateInfo] = []
    for name in discover_template_filenames():
        path = _CERTS_DIR / name
        with Image.open(path) as im:
            w, h = im.size
        calibrated = is_template_calibrated(name, layout)
        tpl_layout = (layout.get("templates") or {}).get(name)
        out.append(
            CertificateTemplateInfo(
                filename=name,
                width=w,
                height=h,
                calibrated=calibrated,
                levels=_levels_for_template(layout, name),
                layout=tpl_layout if isinstance(tpl_layout, dict) else None,
            )
        )
    return out


def uncalibrated_template_names() -> list[str]:
    return [t.filename for t in list_certificate_templates() if not t.calibrated]


def get_template_layout(filename: str) -> dict[str, Any]:
    name = validate_template_filename(filename)
    layout = load_layout()
    tpl = (layout.get("templates") or {}).get(name)
    if not isinstance(tpl, dict):
        raise ValueError(
            f"Template {name!r} has no layout. Calibrate it in Admin → Certificate layout."
        )
    return tpl


def save_template_layout(filename: str, fields: dict[str, Any]) -> dict[str, Any]:
    name = validate_template_filename(filename)
    layout = load_layout(reload=True)
    templates = dict(layout.get("templates") or {})
    templates[name] = {
        "display_name": fields["display_name"],
        "issue_date": fields["issue_date"],
        "signature": fields["signature"],
    }
    layout["templates"] = templates
    canvas_w, canvas_h = _template_canvas_size(name)
    layout["canvas"] = {"width": canvas_w, "height": canvas_h}
    save_layout(layout)
    return templates[name]


def normalize_level(level: str) -> str:
    lv = (level or "").strip().lower()
    if lv not in ("beginner", "intermediate", "advanced"):
        raise ValueError("level must be beginner, intermediate, or advanced")
    return lv


def template_filename_for_level(level: str) -> str:
    layout = load_layout()
    lv = normalize_level(level)
    level_template = layout.get("level_template") or {}
    tpl = str(level_template.get(lv) or "").strip()
    if not tpl:
        raise ValueError(f"No certificate template mapped for level {lv!r}.")
    validate_template_filename(tpl)
    if not is_template_calibrated(tpl, layout):
        raise ValueError(
            f"Certificate template {tpl!r} is not calibrated. "
            "Open Admin → Certificate layout to set name, date, and signature positions."
        )
    return tpl


def template_path_for_level(level: str) -> Path:
    return _CERTS_DIR / template_filename_for_level(level)


def _template_canvas_size(filename: str) -> tuple[int, int]:
    name = validate_template_filename(filename)
    with Image.open(_CERTS_DIR / name) as im:
        return im.size


def signature_path() -> Path:
    layout = load_layout()
    configured = str(layout.get("signature_file") or "signature.png").strip()
    candidates = [configured]
    if configured.lower().endswith(".png"):
        candidates.append("signature.jpg")
    elif configured.lower().endswith(".jpg"):
        candidates.append("signature.png")
    for name in candidates:
        path = _CERTS_DIR / name
        if path.is_file():
            return path
    return _CERTS_DIR / configured


def _load_font(candidates: tuple[str | Path, ...], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for raw in candidates:
        path = Path(raw)
        if not path.is_file():
            continue
        key = (str(path.resolve()), size)
        cached = _font_cache.get(key)
        if cached is not None:
            return cached
        font = ImageFont.truetype(str(path), size=size)
        _font_cache[key] = font
        return font
    key = ("__default__", size)
    cached = _font_cache.get(key)
    if cached is not None:
        return cached
    font = ImageFont.load_default(size=size)
    _font_cache[key] = font
    return font


def _parse_color(value: str) -> tuple[int, int, int, int]:
    s = (value or "#000000").strip()
    if s.startswith("#") and len(s) == 7:
        return (int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16), 255)
    return (0, 0, 0, 255)


def _anchor_xy(
    anchor: str,
    x: int,
    y: int,
    box: tuple[int, int, int, int],
) -> tuple[int, int]:
    left, top, right, bottom = box
    w = right - left
    h = bottom - top
    a = (anchor or "center").lower()
    if a == "left":
        return x, y
    if a == "right":
        return x - w, y
    if a == "baseline":
        return x - w // 2, y - h
    return x - w // 2, y - h // 2


def _resolve_xy(field: dict[str, Any], canvas_w: int, canvas_h: int) -> tuple[int, int]:
    if "x" in field and "y" in field:
        return int(field["x"]), int(field["y"])
    x = int(float(field.get("x_ratio", 0.5)) * canvas_w)
    y = int(float(field.get("y_ratio", 0.5)) * canvas_h)
    return x, y


def _draw_text_field(
    draw: ImageDraw.ImageDraw,
    text: str,
    field: dict[str, Any],
    canvas_w: int,
    canvas_h: int,
    *,
    font_role: str,
) -> None:
    if not text:
        return
    size = int(field.get("size") or 16)
    font = _load_font(
        _NAME_FONT_CANDIDATES if font_role == "name" else _DATE_FONT_CANDIDATES,
        size,
    )
    color = _parse_color(str(field.get("color") or "#000000"))
    x, y = _resolve_xy(field, canvas_w, canvas_h)
    bbox = draw.textbbox((0, 0), text, font=font)
    px, py = _anchor_xy(str(field.get("anchor") or "center"), x, y, bbox)
    draw.text((px, py), text, fill=color, font=font)


def _paste_signature(
    base: Image.Image,
    field: dict[str, Any],
    sig_path: Path,
    canvas_w: int,
    canvas_h: int,
) -> None:
    if not sig_path.is_file():
        return
    sig = Image.open(sig_path).convert("RGBA")
    max_w = int(float(field.get("max_width_ratio", 0.15)) * canvas_w)
    max_h = int(float(field.get("max_height_ratio", 0.07)) * canvas_h)
    sig.thumbnail((max(1, max_w), max(1, max_h)), Image.Resampling.LANCZOS)
    x, y = _resolve_xy(field, canvas_w, canvas_h)
    bbox = (0, 0, sig.width, sig.height)
    px, py = _anchor_xy(str(field.get("anchor") or "center"), x, y, bbox)
    base.paste(sig, (px, py), sig)


def format_issue_date(when: date | None = None) -> str:
    layout = load_layout()
    fmt = str(layout.get("date_format") or "%B %d, %Y")
    return (when or date.today()).strftime(fmt)


def render_certificate_template(
    template_filename: str,
    display_name: str,
    *,
    fields: dict[str, Any] | None = None,
    issue_date: date | None = None,
    signature_file: Path | None = None,
) -> CertificateRenderResult:
    name = validate_template_filename(template_filename)
    display = (display_name or "").strip()
    if not display:
        raise ValueError("display_name is required")

    field_cfg = fields if fields is not None else get_template_layout(name)
    if not is_template_calibrated(name):
        raise ValueError(
            f"Template {name!r} is not calibrated. Use Admin → Certificate layout."
        )

    path = _CERTS_DIR / name
    with Image.open(path) as im:
        base = im.convert("RGBA")
    canvas_w, canvas_h = base.size

    draw = ImageDraw.Draw(base)
    _draw_text_field(
        draw,
        display,
        field_cfg["display_name"],
        canvas_w,
        canvas_h,
        font_role="name",
    )
    _draw_text_field(
        draw,
        format_issue_date(issue_date),
        field_cfg["issue_date"],
        canvas_w,
        canvas_h,
        font_role="date",
    )
    _paste_signature(
        base,
        field_cfg["signature"],
        signature_file or signature_path(),
        canvas_w,
        canvas_h,
    )

    buf = BytesIO()
    base.convert("RGB").save(buf, format="JPEG", quality=95)
    stem = Path(name).stem.lower()
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in display)[:48] or "certificate"
    filename = f"certificate-{stem}-{safe}.jpg"
    return CertificateRenderResult(
        image_bytes=buf.getvalue(),
        media_type="image/jpeg",
        filename=filename,
    )


def render_certificate(
    level: str,
    display_name: str,
    *,
    issue_date: date | None = None,
    signature_file: Path | None = None,
) -> CertificateRenderResult:
    tpl = template_filename_for_level(level)
    result = render_certificate_template(
        tpl,
        display_name,
        issue_date=issue_date,
        signature_file=signature_file,
    )
    lv = normalize_level(level)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in display_name)[:48]
    return CertificateRenderResult(
        image_bytes=result.image_bytes,
        media_type=result.media_type,
        filename=f"certificate-{lv}-{safe or 'certificate'}.jpg",
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def score_qualifies_for_certificate(score: float) -> bool:
    return float(score) > CERTIFICATE_THRESHOLD


def employee_assessment_unit_score(assessment_id: str, employee_id: str) -> float | None:
    from services.attempt_service import normalize_employee_id
    from services.models import Submission
    from services.database import get_session_factory
    from sqlalchemy import select

    eid = normalize_employee_id(employee_id)
    if not eid:
        return None
    with get_session_factory()() as session:
        rows = session.scalars(
            select(Submission).where(Submission.assessment_id == assessment_id)
        ).all()
    scores: list[float] = []
    for r in rows:
        uid = r.user_id or ""
        part = uid.split("|", 1)[0].strip().casefold()
        if part != eid:
            continue
        try:
            raw = float(r.score or 0)
        except (TypeError, ValueError):
            continue
        scores.append(max(0.0, min(1.0, raw / 100.0)))
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


def assert_client_may_generate_certificate(
    assessment_id: str,
    employee_id: str,
) -> tuple[str, float, str | None, str | None]:
    meta = db_service.get_assessment_metadata(assessment_id)
    if not meta.get("certificate_enabled"):
        raise ValueError("Certificate is not enabled for this assessment.")
    level = (meta.get("certificate_level") or "").strip().lower()
    if level not in ("beginner", "intermediate", "advanced"):
        raise ValueError("Certificate level is not configured for this assessment.")
    template_filename_for_level(level)
    score = employee_assessment_unit_score(assessment_id, employee_id)
    if score is None:
        raise ValueError("Submit the assessment before generating a certificate.")
    if not score_qualifies_for_certificate(score):
        raise ValueError("Score does not meet the certificate threshold (> 85%).")
    lang_code = (meta.get("language_code") or "").strip() or None
    lang_label = (meta.get("language_label") or "").strip() or None
    return level, score, lang_code, lang_label


def resolve_certificate_language(
    *,
    assessment_id: str | None = None,
    language_code: str | None = None,
    language_label: str | None = None,
) -> tuple[str | None, str | None]:
    code = (language_code or "").strip() or None
    label = (language_label or "").strip() or None
    if assessment_id:
        meta = db_service.get_assessment_metadata(assessment_id.strip())
        if not code:
            code = (meta.get("language_code") or "").strip() or None
        if not label:
            label = (meta.get("language_label") or "").strip() or None
    return code, label


def list_employee_certificates(employee_id: str) -> list[dict[str, Any]]:
    from services.attempt_service import normalize_employee_id
    from services.database import get_session_factory
    from services.models import CertificateIssued
    from sqlalchemy import select

    eid = normalize_employee_id(employee_id)
    if not eid:
        return []
    with get_session_factory()() as session:
        rows = session.scalars(
            select(CertificateIssued)
            .where(CertificateIssued.employee_id == eid)
            .order_by(CertificateIssued.issued_at.desc())
        ).all()
    return [
        {
            "id": int(r.id),
            "display_name": r.display_name,
            "level": r.level,
            "language_code": (r.language_code or "").strip() or None,
            "language_label": (r.language_label or "").strip() or None,
            "assessment_id": r.assessment_id,
            "score": float(r.score) if r.score is not None else None,
            "issued_at": r.issued_at,
            "issued_by": r.issued_by,
        }
        for r in rows
    ]


def record_certificate_issued(
    *,
    employee_id: str,
    display_name: str,
    level: str,
    assessment_id: str | None = None,
    score: float | None = None,
    issued_by: str = "auto",
    language_code: str | None = None,
    language_label: str | None = None,
) -> int:
    from services.attempt_service import normalize_employee_id
    from services.database import get_session_factory
    from services.models import CertificateIssued

    eid = normalize_employee_id(employee_id)
    if not eid:
        raise ValueError("employee_id is required")
    lv = normalize_level(level)
    lang_code, lang_label = resolve_certificate_language(
        assessment_id=assessment_id,
        language_code=language_code,
        language_label=language_label,
    )
    with get_session_factory()() as session:
        row = CertificateIssued(
            employee_id=eid,
            display_name=(display_name or "").strip(),
            level=lv,
            language_code=lang_code,
            language_label=lang_label,
            assessment_id=(assessment_id or "").strip() or None,
            score=float(score) if score is not None else None,
            issued_at=utc_now_iso(),
            issued_by=(issued_by or "auto").strip() or "auto",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return int(row.id)


def issue_certificate(
    *,
    employee_id: str,
    display_name: str,
    level: str,
    assessment_id: str | None = None,
    score: float | None = None,
    issued_by: str = "auto",
    issue_date: date | None = None,
    language_code: str | None = None,
    language_label: str | None = None,
) -> tuple[CertificateRenderResult, int]:
    result = render_certificate(
        level,
        display_name,
        issue_date=issue_date,
    )
    issued_id = record_certificate_issued(
        employee_id=employee_id,
        display_name=display_name,
        level=level,
        assessment_id=assessment_id,
        score=score,
        issued_by=issued_by,
        language_code=language_code,
        language_label=language_label,
    )
    return result, issued_id


def certificate_offer_from_submit(
    *,
    certificate_enabled: bool,
    certificate_level: str | None,
    language_label: str | None,
    score: float,
) -> dict[str, Any] | None:
    if not certificate_enabled:
        return None
    lv = (certificate_level or "").strip().lower()
    if lv not in ("beginner", "intermediate", "advanced"):
        return None
    if not score_qualifies_for_certificate(score):
        return None
    try:
        template_filename_for_level(lv)
    except ValueError:
        return None
    lang = (language_label or "Python").strip() or "Python"
    return {
        "level": lv,
        "language_label": lang,
        "threshold_percent": int(CERTIFICATE_THRESHOLD * 100),
    }
