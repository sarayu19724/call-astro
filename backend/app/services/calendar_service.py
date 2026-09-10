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

# Short, friendly phrase per house used ONLY for the "Why?" explanation
# bullets (e.g. "This activates topics related to gains and opportunities").
# Purely cosmetic wording on top of already-computed house facts — never a
# new source of truth.
HOUSE_ACTIVATION_PHRASE: Dict[int, str] = {
    1: "self and personal vitality",
    2: "wealth and family",
    3: "courage and communication",
    4: "home and emotional foundation",
    5: "creativity and children",
    6: "work and health routines",
    7: "relationships and partnerships",
    8: "transformation and change",
    9: "fortune and higher learning",
    10: "career and public standing",
    11: "gains and opportunities",
    12: "spirituality and foreign connections",
}

# Human-readable Vedic significance of each topic. These meanings explain the
# already-identified significant topics; they do not decide whether a topic is
# significant. The actual significance still comes from TOPIC_CHART_FACTORS and
# the verified transit relevance calculated below.
TOPIC_SIGNIFICANCE: Dict[str, str] = {
    "career": "The 10th house signifies career, profession, work, status, and public standing.",
    "finance": "The 2nd house signifies accumulated wealth, savings, family resources, and possessions; the 11th house also signifies gains and income.",
    "health": "The 1st house signifies the body, vitality, and overall constitution; the 6th house is examined for illness and health-related challenges.",
    "marriage": "The 7th house signifies marriage, spouse, partnerships, and long-term relationships.",
    "children": "The 5th house signifies children, creativity, intelligence, and progeny-related matters.",
    "education": "The 4th and 5th houses are important for education, learning, intelligence, and academic development.",
    "relationships": "The 7th house signifies partnerships and marriage, while the 11th house can relate to social connections and fulfilment of desires.",
    "travel": "The 3rd, 9th, and 12th houses are considered for travel, journeys, long-distance movement, and foreign connections.",
    "business": "The 7th house signifies business partnerships and trade, while the 10th and 11th houses relate to profession and gains.",
}


def _topic_significance_for(topic: str) -> str:
    key = (topic or "").strip().lower()
    return TOPIC_SIGNIFICANCE.get(key, "This topic is connected to the relevant life area identified from the user's chart factors.")


def _build_topic_factors(planetary_positions: List[Dict[str, Any]], significant_topics: List[str]) -> Dict[str, List[str]]:
    """Build verified, date-specific factors for ONLY the topics already marked significant.

    Each factor comes directly from the calculated transit planet -> sign -> natal house
    relationship. No new topic is created here and no LLM-generated factor is used.
    """
    factors: Dict[str, List[str]] = {topic: [] for topic in significant_topics}
    wanted = set(significant_topics)
    for entry in planetary_positions:
        relevance = entry.get("relevance") or {}
        house = relevance.get("house")
        topics = relevance.get("topics") or []
        if house is None:
            continue
        for topic in topics:
            if topic not in wanted:
                continue
            planet = entry.get("planet")
            sign = entry.get("sign")
            factor = f"{planet} is transiting your {_ordinal(int(house))} house in {sign}, which is connected with {topic}."
            if factor not in factors[topic]:
                factors[topic].append(factor)
    return factors



def _ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


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
# PERSONAL DAY FAVORABILITY
#
# ONLY TWO STATES: "favorable" or "normal". There is no separate
# "caution"/"needs care" state — a day with no relevant event, a purely
# challenging event, or a mix of supportive and challenging events all
# collapse into "normal". This is a deliberate simplification: a
# three-way favorable/caution/normal split made ordinary, unremarkable
# days look like a warning (nearly every day has *some* malefic transit
# somewhere), which was misleading. Now the ONLY thing the calendar ever
# flags positively is a day with a genuinely clean, supportive signal —
# everything else is presented neutrally, with no dot and no red flag.
#
# For a given date, we look at:
#   1. Every planet's transit sign that day -> house from the user's Lagna
#      -> whether that placement is classically supportive (kendra/trikona)
#      for a life area, weighted by whether the planet is a natural
#      benefic or malefic.
#   2. The active Mahadasha lord's nature (benefic/malefic).
#
# STRICT RULE — enforced exactly as written, never relaxed:
#   if supportive_signal and not challenging_signal: -> "favorable"
#   else:                                              -> "normal"
# A day is NEVER anything other than one of these two strings, so every
# consumer downstream (month grid dot, day panel, "Best dates this
# month") can render a single dot/label with no extra logic needed.
# ------------------------------------------------------------------
def _classify_personal_day(
    transit_events: List[Dict[str, Any]],
    dasha_events: List[Dict[str, Any]],
) -> str:
    """Classify a day from actual personalized calendar events only —
    two states, 'favorable' or 'normal'. No numeric score is used. A day
    is favorable only when a relevant transit/Dasha event is directly
    supportive AND nothing relevant is challenging. Mixed or purely
    challenging signals are 'normal', same as no signal at all."""
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
    return "normal"


def _build_personal_reasons(
    transit_events: List[Dict[str, Any]],
    dasha_events: List[Dict[str, Any]],
) -> List[str]:
    """Turns the same sparse events _classify_personal_day looks at into
    plain-language 'Why?' bullets for a FAVORABLE day — never a numeric
    score, never an invented factor. Only genuinely supportive factors
    are surfaced; 'normal' days simply have nothing conclusive to point
    to, so they get no bullets (and the explanation prompt is instructed
    to describe them plainly instead)."""
    supportive: List[str] = []

    for event in transit_events:
        relevance = event.get("relevance", {})
        topics = relevance.get("topics")
        house = relevance.get("house")
        if not topics:
            continue
        planet = event.get("planet")
        if planet not in NATURAL_BENEFICS:
            continue
        phrase = HOUSE_ACTIVATION_PHRASE.get(house, "this area of life") if house else "this area of life"
        house_str = f"your {_ordinal(house)} house" if house else f"{event.get('new_sign')}"
        supportive.append(f"{planet} enters {house_str}")
        supportive.append(f"{planet} is naturally benefic")
        supportive.append(f"This activates topics related to {phrase}")

    for event in dasha_events:
        lord = event.get("mahadasha")
        antar = event.get("antardasha")
        boundary = event.get("boundary")
        if not lord or lord not in NATURAL_BENEFICS:
            continue
        period_label = f"{lord} Mahadasha" + (f" ({antar} Antardasha)" if antar else "")
        verb = "begins" if boundary == "start" else "is in its closing phase" if boundary == "end" else "is active"
        supportive.append(f"{period_label} {verb}")
        supportive.append(f"{lord} is naturally benefic")

    return supportive


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
#
# NOTE: Abhijit and Brahma Muhurta occur on nearly every calendar day by
# classical construction — that's expected and correct, NOT a bug. What
# was misleading before was the MONTH-LEVEL SUMMARY counting these as
# "N days with a favorable Muhurta", which made it look like the calendar
# was singling out special days when it was really just describing a
# routine daily window. That aggregate count has been removed from
# get_month_summary() below; the per-day timings themselves are still
# shown (factually, with real computed times) in the day panel.
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
    # Only actual personalized sign-change/Dasha events contribute. Every
    # day gets EXACTLY ONE of 'favorable' / 'normal' — see
    # _classify_personal_day's strict logic above. There is no third state.
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

    # "Why?" bullets — built from the SAME sparse events that decided the
    # classification above, never a separate/invented explanation. Only
    # populated for favorable days; a 'normal' day has nothing conclusive
    # to list, which is fine and expected.
    supportive_reasons = _build_personal_reasons(day_transit_events, day_dasha_events)

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
        "topic_significance": {topic: _topic_significance_for(topic) for topic in sorted(significant_topics)},
        "topic_factors": _build_topic_factors(planetary_positions, sorted(significant_topics)),
    }


DAY_EXPLAIN_PROMPT = """You are a warm, experienced Indian Vedic Astrologer explaining why one specific
calendar date matters for the client, using ONLY the verified facts below — never invent a planet,
sign, house, topic, or timing that isn't listed.

Rules:
1. Respond STRICTLY in {language}.
2. Length: 2-5 sentences, under 100 words. Plain prose, no bullet points, no headers.
3. Never mention database, score, or technical implementation. Speak naturally as an astrologer.
4. The explanation MUST directly address the topics listed in "Significant topics". Do not introduce
   a different topic. For each listed topic, explain what it signifies in Vedic astrology using the
   provided "Topic meanings", and then connect it to the provided "Verified topic factors".
5. A verified factor must be repeated faithfully. Do not invent an aspect, conjunction, lordship,
   dignity, yoga, or timing that is not explicitly provided.
6. If a topic has no verified factor, say that the topic is identified from the chart relevance, but
   avoid claiming a specific transit caused it.
7. If the personal indication is "favorable", you may describe the listed factors as supportive
   tendencies, never as a guarantee. If it is "normal", remain neutral and do not call it caution.
8. If favorable timing windows are listed, they may be mentioned for planning, but they do not replace
   the explanation of why the significant topics are relevant.

Date: {date}
Personal indication: {personal_status}
Significant topics: {topics}
Topic meanings: {topic_meanings}
Verified topic factors: {topic_factors}
Panchang: {panchang}
Planetary movements on this date (verified): {transits}
Current Dasha period (verified): {dasha}
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
    significant_topic_list = detail.get("significant_topics", [])
    topics_str = ", ".join(significant_topic_list) or "None specifically activated"
    topic_meanings_str = "; ".join(
        f"{topic}: {detail.get('topic_significance', {}).get(topic, _topic_significance_for(topic))}"
        for topic in significant_topic_list
    ) or "None"
    topic_factors_str = "; ".join(
        f"{topic}: {', '.join(detail.get('topic_factors', {}).get(topic, [])) or 'No specific transit factor listed'}"
        for topic in significant_topic_list
    ) or "None"

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

    prompt = DAY_EXPLAIN_PROMPT.format(
        language=language, date=date_str,
        personal_status=detail.get("personal_status", "normal"),
        topics=topics_str,
        topic_meanings=topic_meanings_str,
        topic_factors=topic_factors_str,
        panchang=panchang_str,
        transits=transits_str, dasha=dasha_str,
        good_muhurta=good_str, avoid_muhurta=avoid_str,
    )

    fallback = {
        "English": (
            f"This date is relevant to {topics_str}. "
            f"{topic_factors_str if topic_factors_str != 'None' else 'No specific transit factor is listed for these topics.'} "
            "The favorable timing windows are shown above for planning."
        ),
        "Hindi": (
            f"यह तिथि {topics_str} से संबंधित है। "
            f"{topic_factors_str if topic_factors_str != 'None' else 'इन विषयों के लिए कोई विशिष्ट गोचर कारक सूचीबद्ध नहीं है।'} "
            "योजना के लिए ऊपर दिए गए शुभ मुहूर्त देखे जा सकते हैं।"
        ),
        "Hinglish": (
            f"Yeh date {topics_str} se relevant hai. "
            f"{topic_factors_str if topic_factors_str != 'None' else 'In topics ke liye koi specific transit factor listed nahi hai.'} "
            "Planning ke liye upar diye gaye favorable Muhurta dekhein."
        ),
    }.get(language, "Is date ke liye koi specific explanation available nahi hai.")

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

    # "Favorable dates this month" — plain list of day numbers, NOT a
    # score. This is now the ONLY personal-status count in the summary;
    # the old "N days with a favorable Muhurta" / "N days with a period
    # to avoid" counts have been removed entirely, since Abhijit/Brahma
    # and Rahu Kalam/Yamaganda/Gulika occur on nearly every single day by
    # classical construction — counting them at the month level made
    # ordinary days look either universally auspicious or universally
    # inauspicious, which was misleading. The real per-day timings are
    # still shown, with actual computed times, in the day detail panel.
    favorable_dates = sorted(
        int(day) for day, info in days.items() if info.get("personal_status") == "favorable"
    )
    favorable_days = len(favorable_dates)

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
        "favorable_dates": favorable_dates,
        "most_significant_day": most_significant,
        "swisseph_available": month_data["swisseph_available"],
        "has_dasha_data": month_data["has_dasha_data"],
        "has_chart_data": month_data["has_chart_data"],
        "has_muhurta_data": month_data.get("has_muhurta_data", False),
        "location_source": month_data.get("location_source", "unavailable"),
        "calendar_latitude": month_data.get("calendar_latitude"),
        "calendar_longitude": month_data.get("calendar_longitude"),
    }