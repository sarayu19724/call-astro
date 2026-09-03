from datetime import datetime
from typing import Dict
from app.services.geocoding_service import geocoding_service
from app.services.kundli_service import kundli_service
from app.services.dasha_api_service import dasha_api_service
from app.utils.logger import logger


def _to_24h(time_str: str) -> str:
    if not time_str:
        return ""
    try:
        from dateutil import parser as dateutil_parser
        parsed = dateutil_parser.parse(time_str.strip(), fuzzy=True)
        return parsed.strftime("%H:%M")
    except Exception:
        try:
            parsed_time = datetime.strptime(time_str.strip(), "%I:%M %p")
            return parsed_time.strftime("%H:%M")
        except ValueError:
            return time_str


def fetch_partner_chart_bundle(name: str, dob: str, birth_time: str, birth_place: str) -> Dict:
    """Synchronously fetches Kundli + Dasha for one partner. Raises on an
    unrecoverable failure (bad location/chart); a Dasha-only failure is
    tolerated and returned as dasha_info=None — same 'no Dasha is safer
    than a wrong Dasha' philosophy as the single-user pipeline."""
    coords = geocoding_service.geocode(birth_place)
    if not coords:
        raise ValueError(f"Could not find location: {birth_place}")
    lat, lon = coords
    time_24h = _to_24h(birth_time)

    kundli_data = kundli_service.fetch_kundli(
        name=name or "Partner", date=dob, time=time_24h, latitude=lat, longitude=lon,
    )
    if not kundli_data:
        raise ValueError("Chart calculation failed — please verify birth details.")

    chart_data = kundli_service.extract_chart_data(kundli_data)
    if not chart_data or not chart_data.get("ascendant_sign"):
        raise ValueError("Could not extract chart data from response.")

    dasha_info = None
    dasha_tree = None
    try:
        ascendant_data = kundli_service.get_ascendant_data(kundli_data)
        if ascendant_data:
            dasha_tree = dasha_api_service.fetch_dasha_tree(
                date=dob, time=time_24h, latitude=lat, longitude=lon,
                ascendant_data=ascendant_data,
            )
            if dasha_tree:
                dasha_info = dasha_api_service.find_current_period(dasha_tree)
    except Exception as e:
        logger.warning(f"[CoupleService] Dasha fetch failed for {name}: {e}")

    upcoming_periods = []
    if dasha_tree:
        try:
            upcoming_periods = dasha_api_service.get_upcoming_periods(dasha_tree, months_ahead=84)
        except Exception as e:
            logger.warning(f"[CoupleService] upcoming periods failed for {name}: {e}")

    return {
        "name": name, "dob": dob, "birth_time": birth_time, "birth_place": birth_place,
        "latitude": lat, "longitude": lon,
        "chart": chart_data,
        "dasha_info": dasha_info,
        "upcoming_periods": upcoming_periods,
    }