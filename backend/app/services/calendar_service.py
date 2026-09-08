"""
Astrology Calendar Service — computes planetary transit events, Dasha period
boundaries, Muhurta (auspicious/inauspicious timing windows), and personalized
relevance for a given month or day.

Deterministic core: transit sign-changes and sunrise/sunset come from
pyswisseph (Lahiri sidereal), Dasha boundaries come from the already-cached
dasha_tree_raw (the REAL Dasha API tree — no local Vimshottari fallback,
matching the rest of the codebase). Personalization re-uses
get_house_for_sign() and TOPIC_CHART_FACTORS so "important for me" means the
same thing here as it does in the chat pipeline.

MUHURTA CALCULATION: Rahu Kalam, Yamaganda, Gulika Kalam, Abhijit Muhurta,
and Brahma Muhurta are computed deterministically from sunrise/sunset —
these are well-established, weekday-indexed (or fixed-offset) formulas that
don't depend on Tithi/Nakshatra. Durmuhurtham is intentionally NOT computed:
a correct Durmuhurtham needs the day's Tithi and Nakshatra (a full Panchang
engine), which this system does not yet have. Returning an approximated/
guessed Durmuhurtham would be worse than omitting it — this mirrors how
kundli_report_service.py already handles Shad Bala and live transits:
clearly marked as unavailable rather than faked.

The only LLM call in this file (explain_day) is optional and purely phrases
already-computed facts — same pattern as house_insight_service.py. If a
section's underlying data isn't available (no swisseph, no cached Dasha
tree, no natal chart yet, no lat/lon for Muhurta), that section is simply
omitted from the response rather than faked.
"""
import json
import calendar as pycalendar
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

from app.memory.database import db
from app.services.kundli_service import ZODIAC_SIGNS_ORDER
from app.services.topic_service import get_house_for_sign, TOPIC_CHART_FACTORS, NATURAL_BENEFICS, NATURAL_MALEFICS
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
        "[Calendar] pyswisseph not installed — transit events and Muhurta timings will be "
        "unavailable in the Astrology Calendar. Run: pip install pyswisseph"
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


def _get_planet_sign(jd: float, planet_name: str) -> Optional[str]:
    """Sidereal (Lahiri) sign for one planet at one Julian day, computed
    at 12:00 UTC — sufficient resolution for a monthly sign-change
    overview; not meant to pinpoint the exact hour of ingress."""
    if not SWISSEPH_AVAILABLE:
        return None
    try:
        if planet_name == "Ketu":
            rahu_pos, _ = swe.calc_ut(jd, swe.MEAN_NODE, swe.FLG_SIDEREAL)
            longitude = (rahu_pos[0] + 180.0) % 360.0
        else:
            planet_id = PLANET_IDS.get(planet_name)
            if planet_id is None:
                return None
            result, _ = swe.calc_ut(jd, planet_id, swe.FLG_SIDEREAL)
            longitude = result[0]
        return _sign_for_longitude(longitude)
    except Exception as e:
        logger.error(f"[Calendar] swisseph calc failed for {planet_name} on jd={jd}: {e}")
        return None


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
# MUHURTA / PANCHANG-STYLE TIMING CALCULATION
#
# All of this is computed once from sunrise/sunset — no LLM involvement,
# no invented numbers. Rahu Kalam / Yamaganda / Gulika Kalam divide the
# sunrise-to-sunset window into 8 equal segments and pick a fixed segment
# per weekday (standard, widely published tables). Abhijit Muhurta divides
# the same window into 15 equal muhurtas and takes the 8th (centered on
# solar noon). Brahma Muhurta is the fixed 96-minute window ending 48
# minutes before sunrise. These are all independent of Tithi/Nakshatra,
# unlike Durmuhurtham — which is why Durmuhurtham is left out entirely
# rather than approximated.
# ------------------------------------------------------------------
IST_OFFSET_HOURS = 5.5

# Segment index (1-8) per Python weekday (Monday=0 ... Sunday=6).
RAHU_KALAM_SEGMENT = {6: 8, 0: 2, 1: 7, 2: 5, 3: 6, 4: 4, 5: 3}
YAMAGANDA_SEGMENT = {6: 5, 0: 4, 1: 3, 2: 2, 3: 1, 4: 7, 5: 6}
GULIKA_SEGMENT = {6: 7, 0: 6, 1: 5, 2: 4, 3: 3, 4: 2, 5: 1}


def _revjul_minutes_ut(jd_ut: float) -> float:
    """swe.revjul gives a fractional UT hour for the given Julian day moment;
    convert to minutes-since-UT-midnight of that same calendar day."""
    _, _, _, hour = swe.revjul(jd_ut, swe.GREG_CAL)
    return hour * 60.0


def get_sun_rise_set_minutes(target_date: date, latitude: float, longitude: float) -> Optional[Dict[str, float]]:
    """Returns {"sunrise": minutes_after_local_midnight, "sunset": ...} in
    IST (Asia/Kolkata, matching every other fixed-timezone assumption
    already made elsewhere in this codebase), or None if swisseph is
    unavailable or the rise/set search fails (can happen at extreme
    latitudes, not a concern for Indian birth locations)."""
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


def compute_muhurta_periods(target_date: date, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
    """Returns {"sunrise", "sunset", "good": [...], "avoid": [...]} or None
    if sunrise/sunset couldn't be computed. Each entry in good/avoid has
    name, start, end, note."""
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
    abhijit = {
        "start": _minutes_to_hhmm(sunrise + 7 * muhurta_len),
        "end": _minutes_to_hhmm(sunrise + 8 * muhurta_len),
    }
    brahma = {
        "start": _minutes_to_hhmm(sunrise - 96),
        "end": _minutes_to_hhmm(sunrise - 48),
    }

    return {
        "sunrise": _minutes_to_hhmm(sunrise),
        "sunset": _minutes_to_hhmm(sunset),
        "avoid": [
            {"name": "Rahu Kalam", "start": rahu["start"], "end": rahu["end"],
             "note": "Traditionally avoided for starting important new activities."},
            {"name": "Yamaganda", "start": yama["start"], "end": yama["end"],
             "note": "Traditionally avoided for auspicious beginnings."},
            {"name": "Gulika Kalam", "start": gulika["start"], "end": gulika["end"],
             "note": "Traditionally considered inauspicious for new ventures."},
        ],
        "good": [
            {"name": "Abhijit Muhurta", "start": abhijit["start"], "end": abhijit["end"],
             "note": "Traditionally favorable for beginning important work."},
            {"name": "Brahma Muhurta", "start": brahma["start"], "end": brahma["end"],
             "note": "Traditionally suitable for meditation, study, and spiritual practice."},
        ],
    }


# ------------------------------------------------------------------
# MONTH / DAY VIEWS
# ------------------------------------------------------------------
def get_month_events(session_id: str, year: int, month: int) -> Dict[str, Any]:
    session = db.get_or_create_session(session_id)
    chart = _get_natal_chart(session)
    ascendant_sign = chart["ascendant_sign"] if chart else None
    latitude = session.get("latitude")
    longitude = session.get("longitude")

    days_in_month = pycalendar.monthrange(year, month)[1]
    daily_signs = _daily_signs_for_month(year, month)

    days: Dict[str, Dict[str, Any]] = {
        str(d): {"transits": [], "dasha": [], "good": [], "avoid": [], "is_significant": False}
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
                days[str(day)]["good"] = muhurta["good"]
                days[str(day)]["avoid"] = muhurta["avoid"]

    return {
        "year": year, "month": month,
        "swisseph_available": SWISSEPH_AVAILABLE,
        "has_dasha_data": bool(session.get("dasha_tree_raw")),
        "has_chart_data": chart is not None,
        "has_muhurta_data": has_muhurta_data,
        "days": days,
    }


def get_day_detail(session_id: str, date_str: str) -> Dict[str, Any]:
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return {"available": False, "reason": "invalid_date"}

    session = db.get_or_create_session(session_id)
    chart = _get_natal_chart(session)
    ascendant_sign = chart["ascendant_sign"] if chart else None
    latitude = session.get("latitude")
    longitude = session.get("longitude")

    planetary_positions: List[Dict[str, Any]] = []
    if SWISSEPH_AVAILABLE:
        jd = swe.julday(target_date.year, target_date.month, target_date.day, 12.0)
        for planet in PLANET_ORDER:
            sign = _get_planet_sign(jd, planet)
            if not sign:
                continue
            entry: Dict[str, Any] = {"planet": planet, "sign": sign}
            if ascendant_sign:
                entry["relevance"] = _personal_relevance(sign, ascendant_sign)
            planetary_positions.append(entry)

    active_dasha = _find_active_dasha(session, target_date)
    maha_lord = active_dasha.get("mahadasha") if active_dasha else None
    antar_lord = active_dasha.get("antardasha") if active_dasha else None

    significant_topics = set()
    for entry in planetary_positions:
        significant_topics.update(entry.get("relevance", {}).get("topics", []))

    muhurta = None
    if SWISSEPH_AVAILABLE and latitude and longitude:
        muhurta = compute_muhurta_periods(target_date, latitude, longitude)

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
    }


DAY_EXPLAIN_PROMPT = """You are a warm, experienced Indian Vedic Astrologer explaining why one specific
calendar date matters for your client, using ONLY the verified facts below — never invent a planet,
sign, house placement, or timing that isn't listed.

Rules:
1. Respond STRICTLY in {language}.
2. Length: 2-4 sentences, under 70 words. Plain prose, no bullet points, no headers.
3. Never mention "calendar", "computed", "database", or any technical process — speak as if reading
   their chart directly.
4. If Good/Avoid timings are listed below, you may mention them naturally (e.g. "the Rahu Kalam window
   in the morning") but never invent a time that isn't given.
5. If the facts below are sparse, keep the explanation brief and honest rather than padding it out.

Date: {date}
Planetary movements on this date (verified): {transits}
Current Dasha period (verified): {dasha}
Life areas activated for this client (verified): {topics}
Favorable timing windows today (verified): {good_muhurta}
Timing windows to avoid today (verified): {avoid_muhurta}

Write the explanation now:
"""


def explain_day(session_id: str, date_str: str) -> Dict[str, Any]:
    detail = get_day_detail(session_id, date_str)
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
    good_str = "; ".join(f"{m['name']} {m['start']}-{m['end']}" for m in muhurta["good"]) if muhurta else "Not available"
    avoid_str = "; ".join(f"{m['name']} {m['start']}-{m['end']}" for m in muhurta["avoid"]) if muhurta else "Not available"

    prompt = DAY_EXPLAIN_PROMPT.format(
        language=language, date=date_str, transits=transits_str, dasha=dasha_str, topics=topics_str,
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


def get_month_summary(session_id: str, year: int, month: int) -> Dict[str, Any]:
    month_data = get_month_events(session_id, year, month)
    days = month_data["days"]

    transit_count = sum(len(d["transits"]) for d in days.values())
    dasha_event_count = sum(len(d["dasha"]) for d in days.values())
    good_muhurta_days = sum(1 for d in days.values() if d.get("good"))
    avoid_muhurta_days = sum(1 for d in days.values() if d.get("avoid"))
    significant_days = [
        {"day": int(day), "transits": info["transits"], "dasha": info["dasha"]}
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
            most_significant = {"day": day_info["day"], "topics": sorted(topics)}

    return {
        "year": year, "month": month,
        "transit_count": transit_count,
        "dasha_event_count": dasha_event_count,
        "significant_day_count": len(significant_days),
        "good_muhurta_days": good_muhurta_days,
        "avoid_muhurta_days": avoid_muhurta_days,
        "most_significant_day": most_significant,
        "swisseph_available": month_data["swisseph_available"],
        "has_dasha_data": month_data["has_dasha_data"],
        "has_chart_data": month_data["has_chart_data"],
        "has_muhurta_data": month_data.get("has_muhurta_data", False),
    }