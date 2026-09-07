"""
Full Vedic Kundli PDF report generator.

Deterministic — no LLM calls. Every fact here is either read directly
from the Kundli/Dasha API data or computed via a fixed classical formula
(Navamsha, house-lord lookups). Nothing is invented; a section is simply
omitted if its underlying data cannot be verified, rather than showing
a placeholder or apology message.

D9 SOURCE OF TRUTH (updated):
Previously this trusted the Kundli API's own chart_planet_positions.D9
field first, falling back to our own classical Navamsha calculation only
if the API didn't return one. That was backwards for verification
purposes — if the API's D9 field is itself wrong (e.g. built on a
different house/degree convention than planet_lords), we'd silently
accept it. Now the DETERMINISTIC CLASSICAL CALCULATION is the primary
source, and the API's D9 field is only a fallback for when we can't
resolve a planet's absolute degree at all. See
_log_d9_verification_diagnostics() below for the check that verifies the
degree-field assumption this calculation depends on.
"""
import os
import json
import threading
from datetime import date, datetime
from io import BytesIO
from typing import Dict, List, Optional, Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect, Line, Polygon, String

from app.memory.database import db
from app.services.kundli_service import get_house_lord, ZODIAC_SIGNS_ORDER
from app.services.topic_service import get_house_for_sign, get_sign_for_house
from app.services.dasha_api_service import dasha_api_service
from app.config.settings import settings, BACKEND_DIR
from app.utils.logger import logger

# ------------------------------------------------------------------
# FONT REGISTRATION — Devanagari fix
# ------------------------------------------------------------------
FONT_DIR = os.path.join(str(BACKEND_DIR), "fonts")

LATIN_FONT = "Helvetica"
LATIN_FONT_BOLD = "Helvetica-Bold"
DEVANAGARI_FONT = "Helvetica"
DEVANAGARI_FONT_BOLD = "Helvetica-Bold"
DEVANAGARI_FONT_AVAILABLE = False


def _try_register_fonts():
    global LATIN_FONT, LATIN_FONT_BOLD, DEVANAGARI_FONT, DEVANAGARI_FONT_BOLD, DEVANAGARI_FONT_AVAILABLE

    latin_regular = os.path.join(FONT_DIR, "NotoSans-Regular.ttf")
    latin_bold = os.path.join(FONT_DIR, "NotoSans-Bold.ttf")
    deva_regular = os.path.join(FONT_DIR, "NotoSansDevanagari-Regular.ttf")
    deva_bold = os.path.join(FONT_DIR, "NotoSansDevanagari-Bold.ttf")

    try:
        if os.path.exists(latin_regular) and os.path.exists(latin_bold):
            pdfmetrics.registerFont(TTFont("NotoSans", latin_regular))
            pdfmetrics.registerFont(TTFont("NotoSansBold", latin_bold))
            LATIN_FONT = "NotoSans"
            LATIN_FONT_BOLD = "NotoSansBold"
        else:
            logger.warning(f"[KundliReport] NotoSans font files not found in {FONT_DIR} — falling back to Helvetica.")
    except Exception as e:
        logger.warning(f"[KundliReport] Failed to register NotoSans fonts: {e}")

    try:
        if os.path.exists(deva_regular) and os.path.exists(deva_bold):
            pdfmetrics.registerFont(TTFont("NotoSansDevanagari", deva_regular))
            pdfmetrics.registerFont(TTFont("NotoSansDevanagariBold", deva_bold))
            DEVANAGARI_FONT = "NotoSansDevanagari"
            DEVANAGARI_FONT_BOLD = "NotoSansDevanagariBold"
            DEVANAGARI_FONT_AVAILABLE = True
        else:
            logger.warning(
                f"[KundliReport] Devanagari font files not found in {FONT_DIR} — "
                "Hindi PDF text will render as missing-glyph boxes until added."
            )
    except Exception as e:
        logger.warning(f"[KundliReport] Failed to register Devanagari fonts: {e}")


_try_register_fonts()


def _font_for(language: str, bold: bool = False) -> str:
    if language == "Hindi":
        return DEVANAGARI_FONT_BOLD if bold else DEVANAGARI_FONT
    return LATIN_FONT_BOLD if bold else LATIN_FONT


ACCENT = colors.HexColor("#b45309")
DARK = colors.HexColor("#1e293b")
MUTED = colors.HexColor("#64748b")
LIGHT_BG = colors.HexColor("#f8fafc")
LINE = colors.HexColor("#e2e8f0")

# ------------------------------------------------------------------
# CLASSICAL REFERENCE DATA
# ------------------------------------------------------------------
NAKSHATRA_NAMES = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]
NAKSHATRA_ARC = 360.0 / 27.0

# Navamsha (D9) modality groups — classical, fixed rule:
# Movable signs: navamsha count starts from the same sign.
# Fixed signs: starts from the 9th sign counted from itself (index+8).
# Dual signs: starts from the 5th sign counted from itself (index+4).
MOVABLE_SIGNS = {"Aries", "Cancer", "Libra", "Capricorn"}
FIXED_SIGNS = {"Taurus", "Leo", "Scorpio", "Aquarius"}
DUAL_SIGNS = {"Gemini", "Virgo", "Sagittarius", "Pisces"}
NAVAMSHA_ARC = 30.0 / 9.0  # 3.3333... degrees per navamsha

PLANET_ABBR = {
    "Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me", "Jupiter": "Ju",
    "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke",
}
PLANET_ORDER = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]

LABELS = {
    "English": {
        "title": "JANAM KUNDLI", "subtitle": "Vedic Birth Chart Report",
        "birth_details": "Birth Details", "planetary_positions": "Planetary Positions",
        "d1_chart": "D1 — Birth (Rashi) Chart", "d9_chart": "D9 — Navamsha Chart",
        "house_wise": "House-Wise Breakdown", "conjunctions": "Conjunctions",
        "name": "Name", "dob": "Date of Birth", "time": "Time", "place": "Place",
        "lagna": "Lagna (Ascendant)", "moon_sign": "Moon Sign", "nakshatra": "Nakshatra",
        "planet": "Planet", "sign": "Sign", "house": "House", "degree": "Degree",
        "pada": "Pada", "retro": "Retro",
        "house_col": "House", "lord_col": "Lord", "occupants_col": "Occupants",
        "yoga_info": "Yoga Information",
        "dasha_timeline": "Vimshottari Dasha", "current_dasha": "Current Dasha",
        "mahadasha_table": "Mahadasha Timeline (current & upcoming)",
        "antardasha_current": "Current Antardasha Periods",
        "disclaimer": "This report provides a traditional Vedic astrology interpretation based on the "
                       "supplied birth details and chart. Astrological interpretations are not guaranteed predictions.",
        "mahadasha": "Mahadasha", "antardasha": "Antardasha", "start": "Start", "end": "End",
        "current": "Current", "none_label": "None",
        "no_dasha": "Dasha timing data is not available for this chart right now.",
        "no_full_table": "A detailed upcoming Mahadasha timeline could not be retrieved for this chart.",
    },
    "Hindi": {
        "title": "जन्म कुंडली", "subtitle": "वैदिक जन्म कुंडली रिपोर्ट",
        "birth_details": "जन्म विवरण", "planetary_positions": "ग्रहों की स्थिति",
        "d1_chart": "D1 — जन्म (राशि) कुंडली", "d9_chart": "D9 — नवांश कुंडली",
        "house_wise": "भाव-वार विवरण", "conjunctions": "ग्रह युति",
        "name": "नाम", "dob": "जन्म तिथि", "time": "समय", "place": "स्थान",
        "lagna": "लग्न", "moon_sign": "चंद्र राशि", "nakshatra": "नक्षत्र",
        "planet": "ग्रह", "sign": "राशि", "house": "भाव", "degree": "अंश",
        "pada": "पद", "retro": "वक्री",
        "house_col": "भाव", "lord_col": "स्वामी", "occupants_col": "ग्रह",
        "yoga_info": "योग जानकारी",
        "dasha_timeline": "विंशोत्तरी दशा", "current_dasha": "वर्तमान दशा",
        "mahadasha_table": "महादशा समयरेखा (वर्तमान एवं आगामी)",
        "antardasha_current": "वर्तमान अंतर्दशा अवधियाँ",
        "disclaimer": "यह रिपोर्ट दी गई जन्म तिथि और कुंडली के आधार पर पारंपरिक वैदिक ज्योतिष व्याख्या प्रस्तुत करती है। "
                       "ज्योतिषीय व्याख्याएँ सुनिश्चित भविष्यवाणियाँ नहीं हैं।",
        "mahadasha": "महादशा", "antardasha": "अंतर्दशा", "start": "आरंभ", "end": "समाप्ति",
        "current": "वर्तमान", "none_label": "कोई नहीं",
        "no_dasha": "इस कुंडली के लिए दशा डेटा अभी उपलब्ध नहीं है।",
        "no_full_table": "इस कुंडली के लिए विस्तृत आगामी महादशा समयरेखा प्राप्त नहीं हो सकी।",
    },
    "Hinglish": {
        "title": "JANAM KUNDLI", "subtitle": "Vedic Birth Chart Report",
        "birth_details": "Birth Details", "planetary_positions": "Planetary Positions",
        "d1_chart": "D1 — Birth (Rashi) Chart", "d9_chart": "D9 — Navamsha Chart",
        "house_wise": "House-Wise Breakdown", "conjunctions": "Conjunctions (Yuti)",
        "name": "Name", "dob": "Date of Birth", "time": "Time", "place": "Place",
        "lagna": "Lagna", "moon_sign": "Moon Sign", "nakshatra": "Nakshatra",
        "planet": "Planet", "sign": "Sign", "house": "House", "degree": "Degree",
        "pada": "Pada", "retro": "Retro",
        "house_col": "House", "lord_col": "Lord", "occupants_col": "Planets",
        "yoga_info": "Yoga Information",
        "dasha_timeline": "Vimshottari Dasha", "current_dasha": "Current Dasha",
        "mahadasha_table": "Mahadasha Timeline (current aur upcoming)",
        "antardasha_current": "Current Antardasha Periods",
        "disclaimer": "Yeh report diye gaye birth details aur chart ke aadhar par traditional Vedic astrology "
                       "interpretation deti hai. Astrological interpretations guaranteed predictions nahi hain.",
        "mahadasha": "Mahadasha", "antardasha": "Antardasha", "start": "Start", "end": "End",
        "current": "Current", "none_label": "Koi nahi",
        "no_dasha": "Iss chart ke liye Dasha timing data abhi available nahi hai.",
        "no_full_table": "Iss chart ke liye detailed upcoming Mahadasha timeline retrieve nahi ho saki.",
    },
}


def _styles(language: str):
    body_font = _font_for(language, bold=False)
    bold_font = _font_for(language, bold=True)

    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("ReportTitle", fontName=bold_font, textColor=ACCENT, fontSize=22, spaceAfter=2, leading=26))
    ss.add(ParagraphStyle("ReportSubtitle", fontName=body_font, textColor=MUTED, fontSize=10, spaceAfter=14))
    ss.add(ParagraphStyle("SectionHeading", fontName=bold_font, textColor=DARK, fontSize=13, spaceBefore=14, spaceAfter=6))
    ss.add(ParagraphStyle("SubHeading", fontName=bold_font, textColor=ACCENT, fontSize=11, spaceBefore=10, spaceAfter=4))
    ss.add(ParagraphStyle("Body", fontName=body_font, fontSize=9.5, leading=14, textColor=DARK))
    ss.add(ParagraphStyle("Small", fontName=body_font, fontSize=8.5, leading=12, textColor=MUTED))
    ss.add(ParagraphStyle("Footer", fontName=body_font, fontSize=7.5, leading=10, textColor=MUTED))
    ss.add(ParagraphStyle("TableHead", fontName=bold_font, fontSize=9, textColor=colors.white))
    ss.add(ParagraphStyle("TableCell", fontName=body_font, fontSize=8.5, textColor=DARK, leading=11))
    return ss, body_font, bold_font


# ------------------------------------------------------------------
# CHART DATA HELPERS
# ------------------------------------------------------------------
def _get_verified_chart(session: Dict) -> Optional[Dict]:
    raw = session.get("kundli_raw")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    planets = parsed.get("planets") or []
    ascendant_sign = parsed.get("ascendant_sign")
    if not ascendant_sign or not planets:
        return None
    return {"ascendant_sign": ascendant_sign, "planets": planets}


def _get_full_raw(session: Dict) -> Optional[Dict]:
    raw = session.get("kundli_full_raw")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _get_dasha(session: Dict) -> Optional[Dict]:
    raw = session.get("kundli_dasha")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _get_dasha_tree(session: Dict) -> Optional[Dict]:
    raw = session.get("dasha_tree_raw")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _get_moon_sign(chart: Dict) -> str:
    for p in chart["planets"]:
        if p.get("name") == "Moon":
            return p.get("sign_name", "—")
    return "—"


def _get_absolute_degree(full_raw: Optional[Dict], planet_name: str) -> Optional[float]:
    """Tries planet_lords first (confirmed to carry a 'degree' field, since
    it's what the old Moon-only Nakshatra calc relied on), then falls back
    to scanning planetary_positions for any degree-like field. Returns
    None — never a guessed number — if nothing usable is found.

    IMPORTANT ASSUMPTION THIS RELIES ON: planet_lords[name]["degree"] is
    the planet's ABSOLUTE zodiacal longitude (0-360°), not the degree
    within its current sign (0-30°). See
    _log_d9_verification_diagnostics() below, which checks this
    assumption on every report run by comparing our computed D9 against
    the API's own D9 field — if they disagree for a planet whose degree
    IS present, that's the signal this assumption is wrong for this
    payload shape and needs a fix (e.g. degree % 30 + sign-index * 30).
    """
    if not full_raw:
        return None

    planet_lords = full_raw.get("planet_lords") or {}
    entry = planet_lords.get(planet_name)
    if entry and entry.get("degree") is not None:
        try:
            return float(entry["degree"])
        except (TypeError, ValueError):
            pass

    for p in full_raw.get("planetary_positions") or []:
        if p.get("name") == planet_name:
            for key in ("fullDegree", "full_degree", "degree", "longitude", "long"):
                val = p.get(key)
                if val is not None:
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        continue
    return None


def _planet_longitude_details(full_raw: Optional[Dict], planet_name: str) -> Dict[str, Any]:
    result = {"degree_in_sign": None, "nakshatra": None, "pada": None}
    abs_degree = _get_absolute_degree(full_raw, planet_name)
    if abs_degree is None:
        return result
    try:
        result["degree_in_sign"] = round(abs_degree % 30, 2)
        nak_index = int(abs_degree // NAKSHATRA_ARC) % 27
        result["nakshatra"] = NAKSHATRA_NAMES[nak_index]
        pada = int((abs_degree % NAKSHATRA_ARC) // (NAKSHATRA_ARC / 4)) + 1
        result["pada"] = min(max(pada, 1), 4)
    except Exception:
        pass
    return result


def _format_dms(degree_in_sign: Optional[float]) -> str:
    if degree_in_sign is None:
        return "—"
    deg = int(degree_in_sign)
    minutes = round((degree_in_sign - deg) * 60)
    if minutes == 60:
        deg += 1
        minutes = 0
    return f"{deg}°{minutes:02d}'"


def _get_nakshatra_display(session: Dict) -> str:
    full_raw = _get_full_raw(session)
    details = _planet_longitude_details(full_raw, "Moon")
    if details["nakshatra"]:
        pada_str = f" Pada {details['pada']}" if details["pada"] else ""
        return f"{details['nakshatra']}{pada_str}"
    return "—"


# ------------------------------------------------------------------
# NAVAMSHA (D9) — deterministic classical formula. Computed directly
# from each planet's sign + exact degree, so it never depends on whether
# the Kundli API's chart_planet_positions.D9 field happens to be present
# — and, as of this update, is PREFERRED over that field even when it is
# present. See _get_d9_chart() below.
# ------------------------------------------------------------------
def get_navamsha_sign(sign: str, degree_in_sign: Optional[float]) -> Optional[str]:
    if sign not in ZODIAC_SIGNS_ORDER or degree_in_sign is None:
        return None
    sign_index = ZODIAC_SIGNS_ORDER.index(sign)
    navamsha_num = min(int(degree_in_sign // NAVAMSHA_ARC), 8)

    if sign in MOVABLE_SIGNS:
        start_index = sign_index
    elif sign in FIXED_SIGNS:
        start_index = (sign_index + 8) % 12
    else:  # dual sign
        start_index = (sign_index + 4) % 12

    return ZODIAC_SIGNS_ORDER[(start_index + navamsha_num) % 12]


def _extract_api_divisional(full_raw: Optional[Dict], chart_code: str) -> Optional[Dict]:
    """The API's own divisional-chart data — now used ONLY as a fallback
    when our own classical calculation can't be completed (missing degree
    data). See _get_d9_chart()."""
    if not full_raw:
        return None
    try:
        chart_positions = full_raw.get("chart_planet_positions", {})
        chart = chart_positions.get(chart_code)
        if not chart:
            return None
        ascendant_sign = chart.get("Ascendant", {}).get("sign_name")
        if not ascendant_sign:
            return None
        planets = [
            {"name": name, "sign_name": data.get("sign_name"), "isRetro": "false"}
            for name, data in chart.items() if name != "Ascendant" and data.get("sign_name")
        ]
        return {"ascendant_sign": ascendant_sign, "planets": planets}
    except Exception:
        return None


def _compute_navamsha_chart(chart: Dict, full_raw: Optional[Dict]) -> Optional[Dict]:
    """PRIMARY source for D9 (see _get_d9_chart). Computes it ourselves
    from each planet's sign + degree via the fixed classical formula
    above. Requires the Ascendant's degree to be resolvable; individual
    planets missing degree data are simply omitted from the resulting
    chart rather than guessed."""
    asc_degree = _get_absolute_degree(full_raw, "Ascendant")
    if asc_degree is None:
        return None

    asc_sign = chart["ascendant_sign"]
    d9_ascendant = get_navamsha_sign(asc_sign, asc_degree % 30)
    if not d9_ascendant:
        return None

    d9_planets = []
    for p in chart["planets"]:
        name = p.get("name")
        sign = p.get("sign_name", "")
        abs_deg = _get_absolute_degree(full_raw, name)
        if abs_deg is None:
            continue
        nav_sign = get_navamsha_sign(sign, abs_deg % 30)
        if nav_sign:
            d9_planets.append({"name": name, "sign_name": nav_sign, "isRetro": p.get("isRetro", "false")})

    if not d9_planets:
        return None

    return {"ascendant_sign": d9_ascendant, "planets": d9_planets}


def _get_d9_chart(chart: Dict, full_raw: Optional[Dict]) -> Optional[Dict]:
    """UPDATED SOURCE ORDER: the deterministic classical calculation is
    now primary. The API's own D9 field is only used as a fallback if we
    can't resolve degree data for enough planets to compute D9 ourselves
    (e.g. planet_lords missing, or the API response shape changed)."""
    computed = _compute_navamsha_chart(chart, full_raw)
    if computed:
        return computed
    logger.warning(
        "[KundliReport] Could not compute D9 classically (missing degree data) — "
        "falling back to API's own chart_planet_positions.D9 field."
    )
    return _extract_api_divisional(full_raw, "D9")


# ------------------------------------------------------------------
# D9 VERIFICATION DIAGNOSTICS
# Logs, for every planet, the raw planet_lords degree, what our
# classical formula derives from it, and what the API's own D9 field
# says — side by side. This is what tells you whether
# planet_lords[...]["degree"] is really an ABSOLUTE longitude (0-360°)
# or an in-sign degree (0-30°): if it's absolute, our computed sign and
# the API's D9 sign should agree for every planet the API also returns
# a D9 for. If they consistently disagree by a fixed offset pattern,
# that's the signature of an in-sign-degree misinterpretation.
# Runs automatically on every report generation — check the logs after
# your next PDF run instead of writing a separate debug script.
# ------------------------------------------------------------------
def _log_d9_verification_diagnostics(chart: Dict, full_raw: Optional[Dict], session_id: str = ""):
    if not full_raw:
        logger.warning(f"[D9Verify][{session_id}] No kundli_full_raw available — cannot verify D9 degree data.")
        return

    planet_lords = full_raw.get("planet_lords") or {}
    api_d9 = (full_raw.get("chart_planet_positions") or {}).get("D9") or {}

    logger.info(f"[D9Verify][{session_id}] ===== D9 verification diagnostics =====")

    # Ascendant first, since D9 Ascendant anchors the whole chart.
    asc_entry = planet_lords.get("Ascendant")
    asc_abs_degree = _get_absolute_degree(full_raw, "Ascendant")
    asc_sign = chart.get("ascendant_sign")
    computed_asc_d9 = get_navamsha_sign(asc_sign, asc_abs_degree % 30) if (asc_sign and asc_abs_degree is not None) else None
    api_asc_d9 = api_d9.get("Ascendant", {}).get("sign_name")
    logger.info(
        f"[D9Verify][{session_id}] Ascendant: D1_sign={asc_sign} "
        f"raw_degree_field={asc_entry.get('degree') if asc_entry else 'MISSING'} "
        f"computed_D9={computed_asc_d9} api_D9={api_asc_d9} "
        f"{'MATCH' if (computed_asc_d9 and api_asc_d9 and computed_asc_d9 == api_asc_d9) else 'DIFFERS or unavailable'}"
    )

    for p in chart.get("planets", []):
        name = p.get("name")
        d1_sign = p.get("sign_name")
        entry = planet_lords.get(name)
        raw_degree = entry.get("degree") if entry else None

        abs_degree = _get_absolute_degree(full_raw, name)
        computed_d9 = get_navamsha_sign(d1_sign, abs_degree % 30) if (d1_sign and abs_degree is not None) else None
        api_d9_sign = api_d9.get(name, {}).get("sign_name")

        agreement = "N/A (no API D9 for this planet)"
        if computed_d9 and api_d9_sign:
            agreement = "MATCH" if computed_d9 == api_d9_sign else "*** DIFFERS ***"

        logger.info(
            f"[D9Verify][{session_id}] {name}: D1_sign={d1_sign} "
            f"raw_degree_field={raw_degree} abs_degree_used={abs_degree} "
            f"degree_in_sign={round(abs_degree % 30, 2) if abs_degree is not None else None} "
            f"computed_D9={computed_d9} api_D9={api_d9_sign} -> {agreement}"
        )

    logger.info(f"[D9Verify][{session_id}] ===== end diagnostics — check for '*** DIFFERS ***' above =====")


# ------------------------------------------------------------------
# NORTH INDIAN CHART DRAWING — same geometry as the frontend's
# KundliChart.tsx, rendered as real vector shapes (not a pasted image).
# ------------------------------------------------------------------
_HOUSE_LABEL_POS = [
    (150, 55), (70, 35), (35, 70), (55, 150),
    (35, 230), (70, 265), (150, 245), (230, 265),
    (265, 230), (245, 150), (265, 70), (230, 35),
]


def draw_north_indian_chart(ascendant_sign: str, planets: List[Dict[str, Any]], size: float = 260) -> Drawing:
    scale = size / 300.0
    d = Drawing(size, size)

    def sx(x):
        return x * scale

    def sy(y):
        return (300 - y) * scale

    d.add(Rect(sx(10), sy(290), sx(280) - sx(10), sy(10) - sy(290),
               strokeColor=LINE, strokeWidth=1.2, fillColor=None))
    d.add(Polygon(
        points=[sx(150), sy(10), sx(290), sy(150), sx(150), sy(290), sx(10), sy(150)],
        strokeColor=LINE, strokeWidth=1.2, fillColor=None,
    ))
    for (x1, y1) in [(10, 10), (290, 10), (10, 290), (290, 290)]:
        d.add(Line(sx(x1), sy(y1), sx(150), sy(150), strokeColor=LINE, strokeWidth=1.2))

    ascendant_sign = ascendant_sign or ""
    safe_asc_idx = ZODIAC_SIGNS_ORDER.index(ascendant_sign) if ascendant_sign in ZODIAC_SIGNS_ORDER else 0

    def sign_for_house(house_number: int) -> str:
        idx = (safe_asc_idx + house_number - 1) % 12
        return ZODIAC_SIGNS_ORDER[idx]

    planets_by_house: Dict[int, List[Dict[str, Any]]] = {h: [] for h in range(1, 13)}
    for p in planets:
        sign = p.get("sign_name", "")
        house = get_house_for_sign(sign, ascendant_sign) if ascendant_sign else None
        if house:
            planets_by_house[house].append(p)

    for i, (px, py) in enumerate(_HOUSE_LABEL_POS):
        house_number = i + 1
        sign = sign_for_house(house_number)
        house_planets = planets_by_house.get(house_number, [])

        d.add(String(sx(px), sy(py) + sx(10), sign[:3], fontName=LATIN_FONT, fontSize=6.5 * scale,
                      fillColor=MUTED, textAnchor="middle"))

        planet_str = " ".join(PLANET_ABBR.get(p.get("name", ""), (p.get("name") or "")[:2]) for p in house_planets)
        if planet_str:
            d.add(String(sx(px), sy(py) - sx(2), planet_str, fontName=LATIN_FONT_BOLD, fontSize=8.5 * scale,
                          fillColor=DARK, textAnchor="middle"))
        if any(str(p.get("isRetro", "")).lower() == "true" for p in house_planets):
            d.add(String(sx(px), sy(py) - sx(12), "(R)", fontName=LATIN_FONT, fontSize=6 * scale,
                          fillColor=colors.HexColor("#dc2626"), textAnchor="middle"))

    return d


# ------------------------------------------------------------------
# PLANETARY POSITIONS / HOUSE-WISE / CONJUNCTIONS
# ------------------------------------------------------------------
def _build_full_planet_rows(chart: Dict, full_raw: Optional[Dict], L: Dict) -> List[List[str]]:
    ascendant_sign = chart["ascendant_sign"]
    header = [L["planet"], L["sign"], L["degree"], L["house"], L["nakshatra"], L["pada"], L["retro"]]
    rows = [header]

    ordered = sorted(
        chart["planets"],
        key=lambda p: PLANET_ORDER.index(p["name"]) if p.get("name") in PLANET_ORDER else 99
    )
    for p in ordered:
        name = p.get("name", "")
        sign = p.get("sign_name", "")
        house = get_house_for_sign(sign, ascendant_sign)
        retro = str(p.get("isRetro", "")).lower() == "true"
        details = _planet_longitude_details(full_raw, name)
        rows.append([
            name, sign, _format_dms(details["degree_in_sign"]),
            str(house) if house else "—",
            details["nakshatra"] or "—",
            str(details["pada"]) if details["pada"] else "—",
            "Yes" if retro else "—",
        ])
    return rows


def _build_house_wise_rows(chart: Dict, L: Dict) -> List[List[str]]:
    ascendant_sign = chart["ascendant_sign"]
    header = [L["house_col"], L["sign"], L["lord_col"], L["occupants_col"]]
    rows = [header]

    occupants_by_house: Dict[int, List[str]] = {h: [] for h in range(1, 13)}
    for p in chart["planets"]:
        house = get_house_for_sign(p.get("sign_name", ""), ascendant_sign)
        if house:
            retro_marker = " (R)" if str(p.get("isRetro", "")).lower() == "true" else ""
            occupants_by_house[house].append(f"{p.get('name')}{retro_marker}")

    for h in range(1, 13):
        sign = get_sign_for_house(h, ascendant_sign)
        lord = get_house_lord(h, ascendant_sign)
        occupants = ", ".join(occupants_by_house[h]) if occupants_by_house[h] else L["none_label"]
        rows.append([str(h), sign or "—", lord or "—", occupants])
    return rows


def _find_conjunctions(chart: Dict) -> List[str]:
    ascendant_sign = chart["ascendant_sign"]
    by_house: Dict[int, List[str]] = {}
    for p in chart["planets"]:
        house = get_house_for_sign(p.get("sign_name", ""), ascendant_sign)
        if house:
            by_house.setdefault(house, []).append(p.get("name", ""))

    results = []
    for house, names in sorted(by_house.items()):
        if len(names) >= 2:
            sign = get_sign_for_house(house, ascendant_sign)
            results.append(f"{' + '.join(names)} conjunct in House {house} ({sign})")
    return results


# ------------------------------------------------------------------
# DASHA — full Mahadasha table + current Antardasha breakdown
# ------------------------------------------------------------------
def _build_mahadasha_table_rows(dasha_tree: Optional[Dict], current_maha_lord: Optional[str], L: Dict) -> List[List[str]]:
    if not dasha_tree:
        return []
    try:
        periods = dasha_api_service.get_upcoming_periods(dasha_tree, months_ahead=1200)
    except Exception as e:
        logger.warning(f"[KundliReport] could not build Mahadasha table: {e}")
        return []
    if not periods:
        return []

    grouped: List[Dict[str, Any]] = []
    for p in periods:
        maha = p.get("mahadasha")
        start = (p.get("start") or "").split(" ")[0]
        end = (p.get("end") or "").split(" ")[0]
        if grouped and grouped[-1]["mahadasha"] == maha:
            grouped[-1]["end"] = end
        else:
            grouped.append({"mahadasha": maha, "start": start, "end": end})

    header = [L["mahadasha"], L["start"], L["end"], L["current"]]
    rows = [header]
    for g in grouped:
        is_current = "✓" if g["mahadasha"] == current_maha_lord else ""
        rows.append([g["mahadasha"] or "—", g["start"] or "—", g["end"] or "—", is_current])
    return rows


def _build_current_antardasha_rows(dasha_tree: Optional[Dict], current_maha_lord: Optional[str], L: Dict) -> List[List[str]]:
    if not dasha_tree or not current_maha_lord:
        return []
    try:
        periods = dasha_api_service.get_upcoming_periods(dasha_tree, months_ahead=1200)
    except Exception:
        return []
    relevant = [p for p in periods if p.get("mahadasha") == current_maha_lord]
    if not relevant:
        return []

    header = [L["antardasha"], L["start"], L["end"]]
    rows = [header]
    for p in relevant:
        start = (p.get("start") or "").split(" ")[0]
        end = (p.get("end") or "").split(" ")[0]
        rows.append([p.get("antardasha") or "—", start or "—", end or "—"])
    return rows


# ------------------------------------------------------------------
# TABLE STYLING HELPER
# ------------------------------------------------------------------
def _styled_table(rows: List[List[str]], col_widths: List[float], styles, small: bool = False) -> Table:
    wrapped_rows = []
    for i, row in enumerate(rows):
        style_name = "TableHead" if i == 0 else "TableCell"
        wrapped_rows.append([Paragraph(str(cell), styles[style_name]) for cell in row])

    t = Table(wrapped_rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5 if not small else 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5 if not small else 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


# ------------------------------------------------------------------
# MAIN REPORT BUILDER
# ------------------------------------------------------------------
def generate_kundli_report_pdf(session_id: str, language: str, on_progress=None) -> bytes:
    def _tick(step_key: str):
        if on_progress:
            try:
                on_progress(step_key)
            except Exception as cb_err:
                logger.warning(f"[KundliReport] progress callback failed for '{step_key}': {cb_err}")

    session = db.get_or_create_session(session_id)
    chart = _get_verified_chart(session)
    if not chart:
        raise ValueError("No chart data available for this session.")
    full_raw = _get_full_raw(session)
    _tick("verify_chart")

    # Run the D9 verification diagnostics EVERY time a report is
    # generated — cheap (pure log lines, no extra API calls), and gives
    # you the planet_lords-degree-vs-API-D9 comparison you asked for
    # without needing a separate debug script. Check your server logs
    # for "[D9Verify]" after generating Ananya's report.
    try:
        _log_d9_verification_diagnostics(chart, full_raw, session_id=session_id)
    except Exception as diag_err:
        logger.warning(f"[KundliReport] D9 verification diagnostics failed (non-fatal): {diag_err}")

    L = LABELS.get(language, LABELS["Hinglish"])
    styles, body_font, bold_font = _styles(language)
    dasha_info = _get_dasha(session)
    dasha_tree = _get_dasha_tree(session)
    yoga_text = session.get("yoga_text") or ""

    current_maha_lord = None
    if dasha_info:
        current_maha_lord = (dasha_info.get("current_mahadasha") or {}).get("lord")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm, leftMargin=1.6 * cm, rightMargin=1.6 * cm,
    )
    story = []

    # ================= PAGE 1 — TITLE + BIRTH DETAILS + D1 CHART =================
    story.append(Paragraph(L["title"], styles["ReportTitle"]))
    story.append(Paragraph(L["subtitle"], styles["ReportSubtitle"]))
    story.append(HRFlowable(width="100%", color=ACCENT, thickness=1.2, spaceAfter=12))

    story.append(Paragraph(L["birth_details"], styles["SectionHeading"]))
    birth_rows = [
        [L["name"], session.get("name") or "—"],
        [L["dob"], session.get("dob") or "—"],
        [L["time"], session.get("birth_time") or "—"],
        [L["place"], session.get("birth_place") or "—"],
        [L["lagna"], chart["ascendant_sign"]],
        [L["moon_sign"], _get_moon_sign(chart)],
        [L["nakshatra"], _get_nakshatra_display(session)],
    ]
    birth_table = Table(
        [[Paragraph(f"<b>{r[0]}</b>", styles["TableCell"]), Paragraph(r[1], styles["TableCell"])] for r in birth_rows],
        colWidths=[5 * cm, 10.4 * cm]
    )
    birth_table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
    ]))
    story.append(birth_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph(L["d1_chart"], styles["SectionHeading"]))
    story.append(draw_north_indian_chart(chart["ascendant_sign"], chart["planets"], size=280))
    story.append(PageBreak())
    _tick("d1_chart")

    # ================= PAGE 2 — PLANETARY POSITIONS =================
    story.append(Paragraph(L["planetary_positions"], styles["SectionHeading"]))
    planet_rows = _build_full_planet_rows(chart, full_raw, L)
    story.append(_styled_table(planet_rows, [2.3 * cm, 2.3 * cm, 2 * cm, 1.8 * cm, 3.4 * cm, 1.4 * cm, 1.8 * cm], styles))
    story.append(PageBreak())
    _tick("planetary_positions")

    # ================= PAGE 3 — D9 NAVAMSHA CHART (classical calc primary) =================
    d9 = _get_d9_chart(chart, full_raw)
    if d9:
        story.append(Paragraph(L["d9_chart"], styles["SectionHeading"]))
        story.append(draw_north_indian_chart(d9["ascendant_sign"], d9["planets"], size=280))
        story.append(Spacer(1, 8))
        story.append(Paragraph(f"D9 {L['lagna']}: {d9['ascendant_sign']}", styles["Small"]))
        story.append(PageBreak())
    _tick("d9_chart")

    # ================= HOUSE-WISE + CONJUNCTIONS =================
    story.append(Paragraph(L["house_wise"], styles["SectionHeading"]))
    house_rows = _build_house_wise_rows(chart, L)
    story.append(_styled_table(house_rows, [1.6 * cm, 2.6 * cm, 2.6 * cm, 6 * cm], styles))
    story.append(Spacer(1, 16))

    story.append(Paragraph(L["conjunctions"], styles["SectionHeading"]))
    conjunctions = _find_conjunctions(chart)
    if conjunctions:
        for c in conjunctions:
            story.append(Paragraph(f"• {c}", styles["Body"]))
    else:
        story.append(Paragraph(L["none_label"], styles["Body"]))
    story.append(PageBreak())
    _tick("house_analysis")

    # ================= YOGAS =================
    story.append(Paragraph(L["yoga_info"], styles["SectionHeading"]))
    if yoga_text:
        for line in yoga_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("-"):
                story.append(Paragraph(f"• {line[1:].strip()}", styles["Body"]))
            else:
                story.append(Paragraph(f"<b>{line}</b>", styles["Body"]))
    else:
        story.append(Paragraph(L["none_label"], styles["Body"]))
    story.append(PageBreak())
    _tick("yoga_dignity")

    # ================= DASHA =================
    story.append(Paragraph(L["dasha_timeline"], styles["SectionHeading"]))

    if dasha_info:
        maha = dasha_info.get("current_mahadasha", {}) or {}
        antar = dasha_info.get("current_antardasha", {}) or {}
        praty = dasha_info.get("current_pratyantardasha", {}) or {}

        story.append(Paragraph(L["current_dasha"], styles["SubHeading"]))
        current_lines = []
        if maha.get("lord"):
            start = (maha.get("start") or "").split(" ")[0]
            end = (maha.get("end") or "").split(" ")[0]
            current_lines.append(f"{L['mahadasha']}: <b>{maha['lord']}</b>" + (f" ({start} — {end})" if start and end else ""))
        if antar.get("lord"):
            current_lines.append(f"{L['antardasha']}: <b>{antar['lord']}</b>")
        if praty.get("lord"):
            current_lines.append(f"Pratyantardasha: <b>{praty['lord']}</b>")
        for line in current_lines:
            story.append(Paragraph(line, styles["Body"]))
        story.append(Spacer(1, 12))

        mahadasha_rows = _build_mahadasha_table_rows(dasha_tree, current_maha_lord, L)
        if mahadasha_rows:
            story.append(Paragraph(L["mahadasha_table"], styles["SubHeading"]))
            story.append(_styled_table(mahadasha_rows, [3.5 * cm, 3.5 * cm, 3.5 * cm, 2 * cm], styles, small=True))
            story.append(Spacer(1, 12))
        else:
            story.append(Paragraph(L["no_full_table"], styles["Small"]))

        antar_rows = _build_current_antardasha_rows(dasha_tree, current_maha_lord, L)
        if antar_rows:
            story.append(Paragraph(f"{L['antardasha_current']} ({current_maha_lord})", styles["SubHeading"]))
            story.append(_styled_table(antar_rows, [4 * cm, 4.5 * cm, 4.5 * cm], styles, small=True))
    else:
        story.append(Paragraph(L["no_dasha"], styles["Body"]))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", color=LINE, thickness=0.8, spaceAfter=6))
    story.append(Paragraph(L["disclaimer"], styles["Footer"]))
    story.append(Paragraph(f"Generated on {date.today().strftime('%d %B %Y')} — Call-Astro", styles["Footer"]))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    _tick("build_pdf")
    return pdf_bytes


# ------------------------------------------------------------------
# ASYNC REPORT GENERATION
# ------------------------------------------------------------------
REPORT_STEPS = [
    {"key": "verify_chart", "label": "Verifying your chart"},
    {"key": "d1_chart", "label": "Drawing your birth (D1) chart"},
    {"key": "planetary_positions", "label": "Calculating planetary positions"},
    {"key": "d9_chart", "label": "Computing your Navamsha (D9) chart"},
    {"key": "house_analysis", "label": "Analyzing houses and conjunctions"},
    {"key": "yoga_dignity", "label": "Checking yogas"},
    {"key": "build_pdf", "label": "Creating your PDF"},
]


def _initial_report_progress():
    return [{"key": s["key"], "label": s["label"], "done": False} for s in REPORT_STEPS]


def _report_file_path(session_id: str, language: str) -> str:
    safe_lang = "".join(c for c in language if c.isalnum()) or "Hinglish"
    return os.path.join(settings.REPORTS_DIR, f"{session_id}_{safe_lang}.pdf")


def run_report_generation(session_id: str, language: str):
    progress = _initial_report_progress()
    db.update_session(session_id, {
        "report_status": "generating",
        "report_error": None,
        "report_progress": json.dumps(progress),
        "report_started_at": datetime.utcnow().isoformat(),
        "report_file_path": None,
    })

    def on_progress(step_key: str):
        for p in progress:
            if p["key"] == step_key:
                p["done"] = True
        db.update_session(session_id, {"report_progress": json.dumps(progress)})
        logger.info(f"[KundliReport] session {session_id} — step '{step_key}' done")

    try:
        pdf_bytes = generate_kundli_report_pdf(session_id, language, on_progress=on_progress)
        os.makedirs(settings.REPORTS_DIR, exist_ok=True)
        path = _report_file_path(session_id, language)
        with open(path, "wb") as f:
            f.write(pdf_bytes)
        db.update_session(session_id, {"report_status": "ready", "report_file_path": path})
        logger.info(f"[KundliReport] report READY for session {session_id} ({language}) -> {path}")
    except Exception as e:
        logger.error(f"[KundliReport] generation FAILED for session {session_id}: {e}", exc_info=True)
        db.update_session(session_id, {
            "report_status": "failed",
            "report_error": str(e) or "Report generation failed.",
        })


def start_report_generation_async(session_id: str, language: str):
    thread = threading.Thread(target=run_report_generation, args=(session_id, language), daemon=True)
    thread.start()