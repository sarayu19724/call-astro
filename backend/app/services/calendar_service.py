"""
Astrology Calendar Service — computes planetary transit events, Dasha period
boundaries, full Panchang (Tithi/Nakshatra/Yoga/Karana), Muhurta (auspicious/
inauspicious timing windows including Durmuhurtham), and an event-based PERSONAL day
favorability classification for a given month or day.

ARCHITECTURE (matches the split requested):

                        DATE
                          |
          +---------------+---------------+
          |                               |
   PERSONAL ANALYSIS               GENERAL PANCHANG
          |                               |
   User's Kundli (Lagna)              Tithi
   Daily transits                     Nakshatra
   Active Dasha lord                  Yoga
   Kendra/Trikona/Dusthana            Karana
          |                               |
          v                               v
   day classification                 MUHURTA
     GREEN / RED / NORMAL             Rahu Kalam
                                       Yamaganda
                                       Gulika Kalam
                                       Abhijit Muhurta
                                       Brahma Muhurta
                                       Durmuhurtham

Deterministic core: transit sign-changes, Panchang (Tithi/Nakshatra/Yoga/
Karana), and sunrise/sunset all come from pyswisseph (Lahiri sidereal).
Dasha boundaries come from the already-cached dasha_tree_raw (the REAL Dasha
API tree — no local Vimshottari fallback, matching the rest of the
codebase). Personal "For Me" classification is event-based: only relevant transit
sign changes and Dasha boundary events are considered. No numeric score or
threshold is used; this preserves the earlier sparse, event-driven behavior.

PANCHANG NOTE: Tithi, Nakshatra, and Yoga are computed from exact Sun/Moon
sidereal longitude at local noon — precise, deterministic classical
formulas, not approximations. Karana (half-tithi) is derived the same way.
Durmuhurtham, by contrast, genuinely depends on which published table you
follow (sources disagree on the exact muhurta index per weekday) — the
table used below follows the widely-repeated STRUCTURAL pattern (no
Durmuhurtham on Wednesday, two periods on Tuesday and Friday, one period on
every other day), which is far more consistently agreed upon than the exact
minute-level table. This is flagged here rather than silently presented as
undisputed classical fact, the same way the rest of this file discloses its
assumptions.

The only LLM call in this file (explain_day) is optional and purely phrases
already-computed facts — same pattern as house_insight_service.py. If a
section's underlying data isn't available (no swisseph, no cached Dasha
tree, no natal chart yet, no lat/lon for Muhurta), that section is simply
omitted from the response rather than faked.
"""
import json
import calendar as pycalendar
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

from app.memory.database import db
from app.services.kundli_service import ZODIAC_SIGNS_ORDER
from app.services.topic_service import (
    get_house_for_sign, TOPIC_CHART_FACTORS, NATURAL_BENEFICS, NATURAL_MALEFICS,
    KENDRA_TRIKONA_HOUSES, DUSTHANA_HOUSES,
)
from app.services.dasha_api_service import dasha_api_service
from app.services.llm_service import llm_service
from app.utils.logger import logger

try:
    import swisseph as swe
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    SWISSEPH_AVAILABLE = True
except ImportError:
    SWISSEPH_AVAILABLE = False
    logger.warning(
        "[Calendar] pyswisseph not installed — transit events, Panchang, and Muhurta "
        "timings will be unavailable in the Astrology Calendar. Run: pip install pyswisseph"
    )

PLANET_IDS: Dict[str, int] = {}
if SWISSEPH_AVAILABLE:
    PLANET_IDS = {
        "Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY,
        "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN,
        "Rahu": swe.MEAN_NODE,
    }

PLANET_ORDER = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]

# Reverse map: house number -> life areas it governs (mirrors TOPIC_CHART_FACTORS,
# so "important for me" on the calendar means exactly what it means in chat).
HOUSE_TO_TOPICS: Dict[int, List[str]] = {}
for _topic, _cfg in TOPIC_CHART_FACTORS.items():
    HOUSE_TO_TOPICS.setdefault(_cfg["house"], []).append(_topic)


def _sign_for_longitude(longitude: float) -> str:
    idx = int(longitude // 30) % 12
    return ZODIAC_SIGNS_ORDER[idx]


def _get_planet_longitude(jd: float, planet_name: str) -> Optional[float]:
    """Exact sidereal (Lahiri) ecliptic longitude, 0-360°. Needed (not just
    the sign) for Tithi/Yoga/Karana, which depend on the precise Sun-Moon
    angular difference, not just which sign each occupies."""
    if not SWISSEPH_AVAILABLE:
        return None
    try:
        if planet_name == "Ketu":
            rahu_pos, _ = swe.calc_ut(jd, swe.MEAN_NODE, swe.FLG_SIDEREAL)
            return (rahu_pos[0] + 180.0) % 360.0
        planet_id = PLANET_IDS.get(planet_name)
        if planet_id is None:
            return None
        result, _ = swe.calc_ut(jd, planet_id, swe.FLG_SIDEREAL)
        return result[0]
    except Exception as e:
        logger.error(f"[Calendar] swisseph longitude calc failed for {planet_name} on jd={jd}: {e}")
        return None


def _get_planet_sign(jd: float, planet_name: str) -> Optional[str]:
    """Sidereal (Lahiri) sign for one planet at one Julian day, computed
    at 12:00 UTC — sufficient resolution for a monthly sign-change
    overview; not meant to pinpoint the exact hour of ingress."""
    longitude = _get_planet_longitude(jd, planet_name)
    if longitude is None:
        return None
    return _sign_for_longitude(longitude)


def _daily_signs_for_month(year: int, month: int) -> Dict[str, Dict[int, Optional[str]]]:
    """{planet: {day_of_month: sign}} for every day in the month, PLUS day
    0 = the last day of the previous month, so day 1 can be checked for a
    sign change too."""
    days_in_month = pycalendar.monthrange(year, month)[1]
    result: Dict[str, Dict[int, Optional[str]]] = {p: {} for p in PLANET_ORDER}
    if not SWISSEPH_AVAILABLE:
        return result

    for day_offset in range(-1, days_in_month):
        current_date = date(year, month, 1) + timedelta(days=day_offset)
        jd = swe.julday(current_date.year, current_date.month, current_date.day, 12.0)
        key = current_date.day if day_offset >= 0 else 0
        for planet in PLANET_ORDER:
            result[planet][key] = _get_planet_sign(jd, planet)
    return result


def _get_natal_chart(session: Dict) -> Optional[Dict[str, Any]]:
    cached_raw = session.get("kundli_raw")
    if not cached_raw:
        return None
    try:
        parsed = json.loads(cached_raw)
    except Exception:
        return None
    ascendant_sign = parsed.get("ascendant_sign")
    if not ascendant_sign:
        return None
    return {"ascendant_sign": ascendant_sign, "planets": parsed.get("planets") or []}


def _personal_relevance(new_sign: str, ascendant_sign: str) -> Dict[str, Any]:
    house = get_house_for_sign(new_sign, ascendant_sign)
    topics = HOUSE_TO_TOPICS.get(house, []) if house else []
    return {"house": house, "topics": topics}


def _get_dasha_periods(session: Dict) -> List[Dict[str, Any]]:
    raw_tree = session.get("dasha_tree_raw")
    if not raw_tree:
        return []
    try:
        dasha_tree = json.loads(raw_tree)
        return dasha_api_service.get_upcoming_periods(dasha_tree, months_ahead=1200) or []
    except Exception as e:
        logger.error(f"[Calendar] failed to read dasha periods: {e}")
        return []


def _get_dasha_events_for_range(session: Dict, start_date: date, end_date: date) -> List[Dict[str, Any]]:
    events = []
    for p in _get_dasha_periods(session):
        for label, raw_date in (("start", p.get("start")), ("end", p.get("end"))):
            date_str = (raw_date or "").split(" ")[0]
            if not date_str:
                continue
            try:
                event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            if start_date <= event_date <= end_date:
                events.append({
                    "date": event_date.isoformat(),
                    "type": "dasha",
                    "mahadasha": p.get("mahadasha"),
                    "antardasha": p.get("antardasha"),
                    "boundary": label,
                })
    return events


def _find_active_dasha(session: Dict, target_date: date) -> Optional[Dict[str, str]]:
    for p in _get_dasha_periods(session):
        start_str = (p.get("start") or "").split(" ")[0]
        end_str = (p.get("end") or "").split(" ")[0]
        try:
            p_start = datetime.strptime(start_str, "%Y-%m-%d").date()
            p_end = datetime.strptime(end_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if p_start <= target_date <= p_end:
            return {"mahadasha": p.get("mahadasha"), "antardasha": p.get("antardasha")}
    return None


# ------------------------------------------------------------------
# PERSONAL DAY FAVORABILITY — separate from Panchang/Muhurta entirely.
#
# For a given date, we look at:
#   1. Every planet's transit sign that day -> house from the user's Lagna
#      -> whether that placement is classically supportive (kendra/trikona)
#      or challenging (dusthana), weighted by whether the planet is a
#      natural benefic or malefic.
#   2. The active Mahadasha lord's nature (benefic/malefic).
#
# This mirrors the exact same scoring philosophy already used in
# topic_service._score_chart_signal() / _score_dasha_signal() for chat
# responses — "favorable for you" here means the same thing it means when
# the astrologer chatbot says it. The result is a soft score, not a
# prediction: language stays in "supportive indication" / "challenging
# indication" terms, never "this will happen".
# ------------------------------------------------------------------
def _classify_personal_day(
    transit_events: List[Dict[str, Any]],
    dasha_events: List[Dict[str, Any]],
) -> str:
    """Classify a day from actual personalized calendar events only.

    No numeric score is used. A day is favorable when a relevant transit/Dasha
    event is directly supportive and there is no directly challenging event.
    A day is caution when the relevant event is challenging and there is no
    supportive event. Mixed/no relevant events remain normal.

    This intentionally mirrors the earlier calendar behavior: only actual
    sign-change/Dasha events that are relevant to the user's chart contribute
    to the 'For Me' view; ordinary daily planetary positions are not scored.
    """
    supportive = False
    challenging = False

    for event in transit_events:
        relevance = event.get("relevance", {})
        if not relevance.get("topics"):
            continue
        planet = event.get("planet")
        if planet in NATURAL_BENEFICS:
            supportive = True
        elif planet in NATURAL_MALEFICS:
            challenging = True

    for event in dasha_events:
        lord = event.get("mahadasha")
        if lord in NATURAL_BENEFICS:
            supportive = True
        elif lord in NATURAL_MALEFICS:
            challenging = True

    if supportive and not challenging:
        return "favorable"
    if challenging and not supportive:
        return "caution"
    return "normal"


# ------------------------------------------------------------------
# PANCHANG — Tithi, Nakshatra, Yoga, Karana.
# All computed deterministically from exact Sun/Moon sidereal longitude —
# no LLM, no invented numbers.
# ------------------------------------------------------------------
NAKSHATRA_NAMES = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]

YOGA_NAMES = [
    "Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda",
    "Sukarman", "Dhriti", "Shoola", "Ganda", "Vriddhi", "Dhruva",
    "Vyaghata", "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana",
    "Parigha", "Shiva", "Siddha", "Sadhya", "Shubha", "Shukla",
    "Brahma", "Indra", "Vaidhriti",
]

_TITHI_BASE_NAMES = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi", "Saptami",
    "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi",
]

_KARANA_MOVABLE = ["Bava", "Balava", "Kaulava", "Taitila", "Garaja", "Vanija", "Vishti"]
_KARANA_FIXED_END = ["Shakuni", "Chatushpada", "Naga"]

_ARC_27 = 360.0 / 27.0


def _tithi_name(tithi_num: int) -> Tuple[str, str]:
    """tithi_num is 1-30. Returns (name, paksha)."""
    if tithi_num <= 15:
        paksha = "Shukla"
        name = "Purnima" if tithi_num == 15 else _TITHI_BASE_NAMES[tithi_num - 1]
    else:
        paksha = "Krishna"
        idx = tithi_num - 16
        name = "Amavasya" if tithi_num == 30 else _TITHI_BASE_NAMES[idx]
    return name, paksha


def _karana_name(karana_index: int) -> str:
    """karana_index is 1-60."""
    if karana_index == 1:
        return "Kimstughna"
    if karana_index >= 58:
        return _KARANA_FIXED_END[karana_index - 58]
    return _KARANA_MOVABLE[(karana_index - 2) % 7]


def compute_panchang(target_date: date) -> Optional[Dict[str, Any]]:
    """Returns {"tithi", "paksha", "nakshatra", "nakshatra_pada", "yoga",
    "karana"} computed at local noon for the given date, or None if
    swisseph is unavailable."""
    if not SWISSEPH_AVAILABLE:
        return None
    try:
        # Swiss Ephemeris expects UT. For India, 12:00 IST = 06:30 UTC.
        local_noon_ut = 12.0 - IST_OFFSET_HOURS
        jd = swe.julday(
            target_date.year,
            target_date.month,
            target_date.day,
            local_noon_ut,
        )
        sun_long = _get_planet_longitude(jd, "Sun")
        moon_long = _get_planet_longitude(jd, "Moon")
        if sun_long is None or moon_long is None:
            return None

        diff = (moon_long - sun_long) % 360.0

        tithi_num = int(diff // 12) + 1
        tithi_num = min(tithi_num, 30)
        tithi, paksha = _tithi_name(tithi_num)

        nak_idx = int(moon_long // _ARC_27) % 27
        nakshatra = NAKSHATRA_NAMES[nak_idx]
        pada = int((moon_long % _ARC_27) // (_ARC_27 / 4)) + 1
        pada = min(max(pada, 1), 4)

        yoga_long = (sun_long + moon_long) % 360.0
        yoga_idx = int(yoga_long // _ARC_27) % 27
        yoga = YOGA_NAMES[yoga_idx]

        karana_index = int(diff // 6) + 1
        karana_index = min(karana_index, 60)
        karana = _karana_name(karana_index)

        return {
            "tithi": tithi, "paksha": paksha,
            "nakshatra": nakshatra, "nakshatra_pada": pada,
            "yoga": yoga, "karana": karana,
        }
    except Exception as e:
        logger.error(f"[Calendar] Panchang calculation failed for {target_date}: {e}")
        return None


# ------------------------------------------------------------------
# MUHURTA / TIMING CALCULATION
#
# All computed once from sunrise/sunset — no LLM involvement, no invented
# numbers for Rahu Kalam / Yamaganda / Gulika Kalam / Abhijit / Brahma
# Muhurta, which divide the sunrise-to-sunset window into fixed, weekday-
# indexed segments (standard, widely published tables).
#
# DURMUHURTHAM: see the module docstring — the STRUCTURAL pattern (none on
# Wednesday, two periods on Tuesday/Friday, one period every other day) is
# well agreed upon; the exact muhurta index used below is a best-effort
# reading of commonly published tables, flagged here rather than presented
# as beyond dispute.
# ------------------------------------------------------------------
IST_OFFSET_HOURS = 5.5

# Segment index (1-8) per Python weekday (Monday=0 ... Sunday=6).
RAHU_KALAM_SEGMENT = {6: 8, 0: 2, 1: 7, 2: 5, 3: 6, 4: 4, 5: 3}
YAMAGANDA_SEGMENT = {6: 5, 0: 4, 1: 3, 2: 2, 3: 1, 4: 7, 5: 6}
GULIKA_SEGMENT = {6: 7, 0: 6, 1: 5, 2: 4, 3: 3, 4: 2, 5: 1}

# Durmuhurtham segments as (start_muhurta, end_muhurta) out of 15 equal
# muhurtas spanning sunrise-to-sunset. Weekday keys: Monday=0 ... Sunday=6.
DURMUHURTAM_SEGMENTS: Dict[int, List[Tuple[int, int]]] = {
    6: [(12, 13)],             # Sunday — one period
    0: [(10, 11)],             # Monday — one period
    1: [(4, 5), (9, 10)],      # Tuesday — two periods
    2: [],                     # Wednesday — none
    3: [(8, 9)],                # Thursday — one period
    4: [(4, 5), (6, 7)],        # Friday — two periods
    5: [(2, 3)],                 # Saturday — one period
}


def _revjul_minutes_ut(jd_ut: float) -> float:
    """swe.revjul gives a fractional UT hour for the given Julian day moment;
    convert to minutes-since-UT-midnight of that same calendar day."""
    _, _, _, hour = swe.revjul(jd_ut, swe.GREG_CAL)
    return hour * 60.0


def get_sun_rise_set_minutes(target_date: date, latitude: float, longitude: float) -> Optional[Dict[str, float]]:
    """Returns {"sunrise": minutes_after_local_midnight, "sunset": ...} in
    IST (Asia/Kolkata, matching every other fixed-timezone assumption
    already made elsewhere in this codebase), or None if swisseph is
    unavailable or the rise/set search fails."""
    if not SWISSEPH_AVAILABLE:
        return None
    try:
        jd_start_ut = swe.julday(target_date.year, target_date.month, target_date.day, 0.0) - (IST_OFFSET_HOURS / 24.0)
        geopos = (longitude, latitude, 0.0)

        ret_r, tret_r = swe.rise_trans(jd_start_ut, swe.SUN, swe.CALC_RISE, geopos)
        ret_s, tret_s = swe.rise_trans(jd_start_ut, swe.SUN, swe.CALC_SET, geopos)
        if ret_r != 0 or ret_s != 0:
            logger.warning(f"[Calendar] rise/set search failed for {target_date} at ({latitude},{longitude})")
            return None

        sunrise_minutes = (_revjul_minutes_ut(tret_r[0]) + IST_OFFSET_HOURS * 60.0) % 1440
        sunset_minutes = (_revjul_minutes_ut(tret_s[0]) + IST_OFFSET_HOURS * 60.0) % 1440
        if sunset_minutes < sunrise_minutes:
            sunset_minutes += 1440

        return {"sunrise": sunrise_minutes, "sunset": sunset_minutes}
    except Exception as e:
        logger.error(f"[Calendar] sunrise/sunset calculation failed for {target_date}: {e}")
        return None


def _minutes_to_hhmm(minutes: float) -> str:
    total = round(minutes) % 1440
    hh, mm = divmod(total, 60)
    period = "AM" if hh < 12 else "PM"
    display_hh = hh % 12 or 12
    return f"{display_hh}:{mm:02d} {period}"


def _durmuhurtam_periods(weekday: int, sunrise: float, muhurta_len: float) -> List[Dict[str, str]]:
    segments = DURMUHURTAM_SEGMENTS.get(weekday, [])
    periods = []
    for i, (start_idx, end_idx) in enumerate(segments):
        start = sunrise + (start_idx - 1) * muhurta_len
        end = sunrise + end_idx * muhurta_len
        label = "Durmuhurtham" if len(segments) == 1 else f"Durmuhurtham {i + 1}"
        periods.append({
            "name": label,
            "start": _minutes_to_hhmm(start),
            "end": _minutes_to_hhmm(end),
            "note": "Traditionally considered an inauspicious window for starting new ventures.",
        })
    return periods


def compute_muhurta_periods(target_date: date, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
    """Return separately named Muhurta windows for one date."""
    sun_times = get_sun_rise_set_minutes(target_date, latitude, longitude)
    if not sun_times:
        return None

    sunrise = sun_times["sunrise"]
    sunset = sun_times["sunset"]
    day_duration = sunset - sunrise
    if day_duration <= 0:
        return None

    weekday = target_date.weekday()  # Monday=0 ... Sunday=6
    segment_len = day_duration / 8.0

    def _segment(idx: int) -> Dict[str, str]:
        start = sunrise + (idx - 1) * segment_len
        end = sunrise + idx * segment_len
        return {"start": _minutes_to_hhmm(start), "end": _minutes_to_hhmm(end)}

    rahu = _segment(RAHU_KALAM_SEGMENT[weekday])
    yama = _segment(YAMAGANDA_SEGMENT[weekday])
    gulika = _segment(GULIKA_SEGMENT[weekday])

    muhurta_len = day_duration / 15.0

    # The selected reference table used for this calendar does not list
    # Abhijit Muhurta on Wednesday. Keep it separate from Durmuhurtham.
    abhijit = None
    if weekday != 2:  # Wednesday
        abhijit = {
            "start": _minutes_to_hhmm(sunrise + 7 * muhurta_len),
            "end": _minutes_to_hhmm(sunrise + 8 * muhurta_len),
        }

    brahma = {
        "start": _minutes_to_hhmm(sunrise - 96),
        "end": _minutes_to_hhmm(sunrise - 48),
    }

    durmuhurtham = _durmuhurtam_periods(
        weekday,
        sunrise,
        muhurta_len,
    )

    return {
        "sunrise": _minutes_to_hhmm(sunrise),
        "sunset": _minutes_to_hhmm(sunset),
        "abhijit": ([{
            "name": "Abhijit Muhurta",
            "start": abhijit["start"],
            "end": abhijit["end"],
            "note": "Traditionally favorable for beginning important work.",
        }] if abhijit else []),
        "brahma": [{
            "name": "Brahma Muhurta",
            "start": brahma["start"],
            "end": brahma["end"],
            "note": "Traditionally suitable for meditation, study, and spiritual practice.",
        }],
        "rahu_kalam": [{
            "name": "Rahu Kalam",
            "start": rahu["start"],
            "end": rahu["end"],
            "note": "Traditionally avoided for starting important new activities.",
        }],
        "yamaganda": [{
            "name": "Yamaganda",
            "start": yama["start"],
            "end": yama["end"],
            "note": "Traditionally avoided for auspicious beginnings.",
        }],
        "gulika_kalam": [{
            "name": "Gulika Kalam",
            "start": gulika["start"],
            "end": gulika["end"],
            "note": "Traditionally considered unsuitable for some new beginnings.",
        }],
        "durmuhurtham": durmuhurtham,
    }


# ------------------------------------------------------------------
# CALENDAR LOCATION
# ------------------------------------------------------------------
# Birth coordinates remain authoritative for the natal Kundli/Dasha.
# The calendar can receive current browser coordinates for location-dependent
# sunrise/sunset and Muhurta calculations. If current coordinates are absent,
# the existing birth-location coordinates are used as a fallback.
# ------------------------------------------------------------------
def _valid_coordinate(value: Any, minimum: float, maximum: float) -> bool:
    try:
        numeric = float(value)
        return minimum <= numeric <= maximum
    except (TypeError, ValueError):
        return False


def _resolve_calendar_location(
    session: Dict[str, Any],
    current_latitude: Optional[float] = None,
    current_longitude: Optional[float] = None,
) -> Tuple[Optional[float], Optional[float], str]:
    if (
        current_latitude is not None
        and current_longitude is not None
        and _valid_coordinate(current_latitude, -90.0, 90.0)
        and _valid_coordinate(current_longitude, -180.0, 180.0)
    ):
        return float(current_latitude), float(current_longitude), "current"

    birth_latitude = session.get("latitude")
    birth_longitude = session.get("longitude")
    if (
        birth_latitude is not None
        and birth_longitude is not None
        and _valid_coordinate(birth_latitude, -90.0, 90.0)
        and _valid_coordinate(birth_longitude, -180.0, 180.0)
    ):
        return float(birth_latitude), float(birth_longitude), "birth"

    return None, None, "unavailable"


# ------------------------------------------------------------------
# MONTH / DAY VIEWS
# ------------------------------------------------------------------
def get_month_events(
    session_id: str,
    year: int,
    month: int,
    current_latitude: Optional[float] = None,
    current_longitude: Optional[float] = None,
) -> Dict[str, Any]:
    session = db.get_or_create_session(session_id)
    chart = _get_natal_chart(session)
    ascendant_sign = chart["ascendant_sign"] if chart else None
    latitude, longitude, location_source = _resolve_calendar_location(
        session, current_latitude, current_longitude
    )

    days_in_month = pycalendar.monthrange(year, month)[1]
    daily_signs = _daily_signs_for_month(year, month)

    days: Dict[str, Dict[str, Any]] = {
        str(d): {
            "transits": [],
            "dasha": [],
            "muhurta": None,
            "is_significant": False,
            "personal_status": "normal",
        }
        for d in range(1, days_in_month + 1)
    }

    if SWISSEPH_AVAILABLE:
        for planet in PLANET_ORDER:
            signs_by_day = daily_signs.get(planet, {})
            for day in range(1, days_in_month + 1):
                today_sign = signs_by_day.get(day)
                yesterday_sign = signs_by_day.get(day - 1)
                if today_sign and yesterday_sign and today_sign != yesterday_sign:
                    event: Dict[str, Any] = {"planet": planet, "new_sign": today_sign}
                    if ascendant_sign:
                        event["relevance"] = _personal_relevance(today_sign, ascendant_sign)
                    days[str(day)]["transits"].append(event)
                    if event.get("relevance", {}).get("topics"):
                        days[str(day)]["is_significant"] = True

    start_date = date(year, month, 1)
    end_date = date(year, month, days_in_month)
    for ev in _get_dasha_events_for_range(session, start_date, end_date):
        d = str(datetime.strptime(ev["date"], "%Y-%m-%d").date().day)
        days[d]["dasha"].append(ev)
        days[d]["is_significant"] = True

    has_muhurta_data = bool(SWISSEPH_AVAILABLE and latitude and longitude)
    if has_muhurta_data:
        for day in range(1, days_in_month + 1):
            muhurta = compute_muhurta_periods(date(year, month, day), latitude, longitude)
            if muhurta:
                days[str(day)]["muhurta"] = muhurta

    # --- Personal day classification: event-based, no numeric score ---
    # Only actual personalized sign-change/Dasha events contribute.
    if ascendant_sign:
        for day in range(1, days_in_month + 1):
            info = days[str(day)]
            info["personal_status"] = _classify_personal_day(
                info["transits"], info["dasha"]
            )

    return {
        "year": year, "month": month,
        "swisseph_available": SWISSEPH_AVAILABLE,
        "has_dasha_data": bool(session.get("dasha_tree_raw")),
        "has_chart_data": chart is not None,
        "has_muhurta_data": has_muhurta_data,
        "location_source": location_source,
        "calendar_latitude": latitude,
        "calendar_longitude": longitude,
        "days": days,
    }


def get_day_detail(
    session_id: str,
    date_str: str,
    current_latitude: Optional[float] = None,
    current_longitude: Optional[float] = None,
) -> Dict[str, Any]:
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return {"available": False, "reason": "invalid_date"}

    session = db.get_or_create_session(session_id)
    chart = _get_natal_chart(session)
    ascendant_sign = chart["ascendant_sign"] if chart else None
    latitude, longitude, location_source = _resolve_calendar_location(
        session, current_latitude, current_longitude
    )

    planetary_positions: List[Dict[str, Any]] = []
    day_signs: Dict[str, Optional[str]] = {}
    if SWISSEPH_AVAILABLE:
        jd = swe.julday(target_date.year, target_date.month, target_date.day, 12.0)
        for planet in PLANET_ORDER:
            sign = _get_planet_sign(jd, planet)
            day_signs[planet] = sign
            if not sign:
                continue
            entry: Dict[str, Any] = {"planet": planet, "sign": sign}
            if ascendant_sign:
                entry["relevance"] = _personal_relevance(sign, ascendant_sign)
            planetary_positions.append(entry)

    active_dasha = _find_active_dasha(session, target_date)
    maha_lord = active_dasha.get("mahadasha") if active_dasha else None
    antar_lord = active_dasha.get("antardasha") if active_dasha else None

    day_dasha_events = _get_dasha_events_for_range(session, target_date, target_date)

    significant_topics = set()
    for entry in planetary_positions:
        significant_topics.update(entry.get("relevance", {}).get("topics", []))

    # For the selected day, classify only actual sign-change events, matching
    # the month-level For Me logic.
    day_transit_events: List[Dict[str, Any]] = []
    if SWISSEPH_AVAILABLE and ascendant_sign:
        prev_jd = swe.julday(
            (target_date - timedelta(days=1)).year,
            (target_date - timedelta(days=1)).month,
            (target_date - timedelta(days=1)).day,
            12.0,
        )
        for planet in PLANET_ORDER:
            current_sign = day_signs.get(planet)
            previous_sign = _get_planet_sign(prev_jd, planet)
            if current_sign and previous_sign and current_sign != previous_sign:
                day_transit_events.append({
                    "planet": planet,
                    "new_sign": current_sign,
                    "relevance": _personal_relevance(current_sign, ascendant_sign),
                })

    muhurta = None
    if SWISSEPH_AVAILABLE and latitude and longitude:
        muhurta = compute_muhurta_periods(target_date, latitude, longitude)

    panchang = compute_panchang(target_date) if SWISSEPH_AVAILABLE else None

    personal_status = _classify_personal_day(day_transit_events, day_dasha_events)
    supportive_reasons: List[str] = [
        f"{e['planet']} moved into {e['new_sign']}"
        for e in day_transit_events
        if e.get("planet") in NATURAL_BENEFICS and e.get("relevance", {}).get("topics")
    ]
    challenging_reasons: List[str] = [
        f"{e['planet']} moved into {e['new_sign']}"
        for e in day_transit_events
        if e.get("planet") in NATURAL_MALEFICS and e.get("relevance", {}).get("topics")
    ]

    is_auspicious = bool(
        maha_lord and maha_lord in NATURAL_BENEFICS
        and (not antar_lord or antar_lord not in NATURAL_MALEFICS)
        and significant_topics
    )

    return {
        "available": True,
        "date": date_str,
        "planetary_positions": planetary_positions,
        "current_mahadasha": maha_lord,
        "current_antardasha": antar_lord,
        "significant_topics": sorted(significant_topics),
        "is_auspicious_heuristic": is_auspicious,
        "swisseph_available": SWISSEPH_AVAILABLE,
        "has_dasha_data": bool(session.get("dasha_tree_raw")),
        "muhurta": muhurta,
        "has_muhurta_data": muhurta is not None,
        "location_source": location_source,
        "calendar_latitude": latitude,
        "calendar_longitude": longitude,
        "panchang": panchang,
        "personal_status": personal_status,
        "personal_supportive_reasons": supportive_reasons,

        "personal_challenging_reasons": challenging_reasons,
    }


DAY_EXPLAIN_PROMPT = """You are a warm, experienced Indian Vedic Astrologer explaining why one specific
calendar date matters for your client, using ONLY the verified facts below — never invent a planet,
sign, house placement, or timing that isn't listed.

Rules:
1. Respond STRICTLY in {language}.
2. Length: 2-4 sentences, under 70 words. Plain prose, no bullet points, no headers.
3. Never mention "calendar", "computed", "database", "score", or any technical process — speak as if
   reading their chart directly.
4. Frame the personal indication as "supportive" or "needs a bit more care" — NEVER as a guarantee or
   a definite outcome. This is a tendency to be aware of, not a prediction.
5. If Good/Avoid timings are listed below, you may mention them naturally (e.g. "the Rahu Kalam window
   in the morning") but never invent a time that isn't given.
6. If the facts below are sparse, keep the explanation brief and honest rather than padding it out.

Date: {date}
Personal indication: {personal_status} (supportive factors: {supportive}; factors needing care: {challenging})
Panchang: {panchang}
Planetary movements on this date (verified): {transits}
Current Dasha period (verified): {dasha}
Life areas activated for this client (verified): {topics}
Favorable timing windows today (verified): {good_muhurta}
Timing windows to avoid today (verified): {avoid_muhurta}

Write the explanation now:
"""


def explain_day(
    session_id: str,
    date_str: str,
    current_latitude: Optional[float] = None,
    current_longitude: Optional[float] = None,
) -> Dict[str, Any]:
    detail = get_day_detail(session_id, date_str, current_latitude, current_longitude)
    if not detail.get("available"):
        return detail

    session = db.get_or_create_session(session_id)
    language = session.get("language", "Hinglish")

    transits_str = "; ".join(
        f"{p['planet']} in {p['sign']}" for p in detail["planetary_positions"]
    ) or "No transit data available"
    dasha_str = (
        f"Mahadasha {detail['current_mahadasha']}"
        + (f", Antardasha {detail['current_antardasha']}" if detail.get("current_antardasha") else "")
    ) if detail.get("current_mahadasha") else "Not available"
    topics_str = ", ".join(detail.get("significant_topics", [])) or "None specifically activated"

    muhurta = detail.get("muhurta")

    favorable_windows: List[Dict[str, str]] = []
    avoid_windows: List[Dict[str, str]] = []

    if muhurta:
        favorable_windows.extend(muhurta.get("abhijit", []))
        favorable_windows.extend(muhurta.get("brahma", []))
        avoid_windows.extend(muhurta.get("rahu_kalam", []))
        avoid_windows.extend(muhurta.get("yamaganda", []))
        avoid_windows.extend(muhurta.get("gulika_kalam", []))
        avoid_windows.extend(muhurta.get("durmuhurtham", []))

    good_str = "; ".join(
        f"{m['name']} {m['start']}-{m['end']}"
        for m in favorable_windows
    ) or "Not available"

    avoid_str = "; ".join(
        f"{m['name']} {m['start']}-{m['end']}"
        for m in avoid_windows
    ) or "Not available"

    panchang = detail.get("panchang")
    panchang_str = (
        f"{panchang['paksha']} Paksha {panchang['tithi']}, {panchang['nakshatra']} Nakshatra "
        f"(Pada {panchang['nakshatra_pada']}), {panchang['yoga']} Yoga, {panchang['karana']} Karana"
    ) if panchang else "Not available"

    supportive_str = "; ".join(detail.get("personal_supportive_reasons", [])) or "None specifically identified"
    challenging_str = "; ".join(detail.get("personal_challenging_reasons", [])) or "None specifically identified"

    prompt = DAY_EXPLAIN_PROMPT.format(
        language=language, date=date_str,
        personal_status=detail.get("personal_status", "normal"),
        supportive=supportive_str, challenging=challenging_str,
        panchang=panchang_str,
        transits=transits_str, dasha=dasha_str, topics=topics_str,
        good_muhurta=good_str, avoid_muhurta=avoid_str,
    )

    fallback = {
        "English": "This date doesn't show any strongly activated factors in your chart right now.",
        "Hindi": "इस तिथि के लिए आपकी कुंडली में फिलहाल कोई विशेष सक्रिय कारक नहीं दिख रहा।",
        "Hinglish": "Is date ke liye aapki kundli mein abhi koi khaas activated factor nahi dikh raha.",
    }.get(language, "Is date ke liye koi khaas jaankari nahi hai.")

    try:
        explanation = llm_service.generate(prompt=prompt, temperature=0.6).strip() or fallback
    except Exception as e:
        logger.error(f"[Calendar] explain_day LLM failed: {e}")
        explanation = fallback

    detail["explanation"] = explanation
    return detail


def get_month_summary(
    session_id: str,
    year: int,
    month: int,
    current_latitude: Optional[float] = None,
    current_longitude: Optional[float] = None,
) -> Dict[str, Any]:
    month_data = get_month_events(
        session_id, year, month, current_latitude, current_longitude
    )
    days = month_data["days"]

    transit_count = sum(len(d["transits"]) for d in days.values())
    dasha_event_count = sum(len(d["dasha"]) for d in days.values())

    favorable_days = sum(
        1 for d in days.values() if d.get("personal_status") == "favorable"
    )
    caution_days = sum(
        1 for d in days.values() if d.get("personal_status") == "caution"
    )

    good_muhurta_days = sum(
        1 for d in days.values()
        if d.get("muhurta") and (
            d["muhurta"].get("abhijit") or d["muhurta"].get("brahma")
        )
    )
    avoid_muhurta_days = sum(
        1 for d in days.values()
        if d.get("muhurta") and (
            d["muhurta"].get("rahu_kalam")
            or d["muhurta"].get("yamaganda")
            or d["muhurta"].get("gulika_kalam")
            or d["muhurta"].get("durmuhurtham")
        )
    )

    significant_days = [
        {
            "day": int(day),
            "transits": info["transits"],
            "dasha": info["dasha"],
        }
        for day, info in sorted(days.items(), key=lambda kv: int(kv[0]))
        if info["is_significant"]
    ]

    most_significant = None
    best_count = 0
    for day_info in significant_days:
        topics = set()
        for t in day_info["transits"]:
            topics.update(t.get("relevance", {}).get("topics", []))
        if topics and len(topics) > best_count:
            best_count = len(topics)
            most_significant = {
                "day": day_info["day"],
                "topics": sorted(topics),
            }

    return {
        "year": year,
        "month": month,
        "transit_count": transit_count,
        "dasha_event_count": dasha_event_count,
        "significant_day_count": len(significant_days),
        "favorable_days": favorable_days,
        "caution_days": caution_days,
        "good_muhurta_days": good_muhurta_days,
        "avoid_muhurta_days": avoid_muhurta_days,
        "most_significant_day": most_significant,
        "swisseph_available": month_data["swisseph_available"],
        "has_dasha_data": month_data["has_dasha_data"],
        "has_chart_data": month_data["has_chart_data"],
        "has_muhurta_data": month_data.get("has_muhurta_data", False),
        "location_source": month_data.get("location_source", "unavailable"),
        "calendar_latitude": month_data.get("calendar_latitude"),
        "calendar_longitude": month_data.get("calendar_longitude"),
    }
