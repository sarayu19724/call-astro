import json
import urllib.request
import urllib.error
from typing import Optional, Dict
from app.utils.logger import logger

FUNCTION_URL = "https://vutgjzjv7ilckzs7ooeh5gnnyy0xnkdz.lambda-url.ap-south-1.on.aws/"

SIGN_LORDS = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Mars",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}

ZODIAC_SIGNS_ORDER = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]


def get_house_lord(house_number: int, ascendant_sign: str) -> Optional[str]:
    try:
        asc_idx = ZODIAC_SIGNS_ORDER.index(ascendant_sign)
        house_sign = ZODIAC_SIGNS_ORDER[(asc_idx + house_number - 1) % 12]
        return SIGN_LORDS.get(house_sign)
    except (ValueError, KeyError):
        return None


class KundliService:
    def fetch_kundli(self, name: str, date: str, time: str, latitude: float, longitude: float,
                      timezone_name: str = "Asia/Kolkata", language: str = "English",
                      max_retries: int = 2) -> Optional[Dict]:
        payload = {
            "requirements": ["KundliDetails", "AscendantPrediction"],
            "date": date, "time": time,
            "latitude": str(latitude), "longitude": str(longitude),
            "timezone_name": timezone_name, "language": language, "name": name,
        }
        req = urllib.request.Request(
            FUNCTION_URL, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )

        last_error = None
        for attempt in range(1, max_retries + 2):
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    response = json.loads(resp.read().decode("utf-8"))
                logger.info(f"Kundli data fetched successfully (attempt {attempt})")
                return response
            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8")
                logger.warning(f"Kundli fetch HTTP error {e.code} on attempt {attempt}: {error_body}")
                last_error = e
            except Exception as e:
                logger.warning(f"Kundli fetch failed on attempt {attempt}: {e}")
                last_error = e

        logger.error(f"Kundli fetch failed after {max_retries + 1} attempts: {last_error}")
        return None

    def get_ascendant_data(self, kundli_data: Dict) -> Optional[Dict]:
        """Extract the raw Ascendant planet object from planetary_positions —
        required as input for the separate Dasha Lambda's ascendant_data field
        ('Missing required parameters: ascendant_data' otherwise)."""
        try:
            for p in kundli_data.get("planetary_positions", []):
                if p.get("name") == "Ascendant":
                    return p
        except Exception as e:
            logger.error(f"Failed to extract ascendant_data: {e}")
        return None

    def summarize_kundli(self, kundli_data: Dict, dob: Optional[str] = None,
                          dasha_info: Optional[Dict] = None) -> str:
        """dasha_info now comes EXCLUSIVELY from the real Dasha API
        (dasha_api_service), fetched once in chat_service._fetch_dasha_bundle
        and passed in here. The local Vimshottari calculation has been
        REMOVED — it silently produced an incorrect Mahadasha/Antardasha
        lord (Mercury, when the verified correct value is Venus). It's far
        safer to say 'not available' than to state a confidently wrong
        Dasha in an astrology reading."""
        try:
            lines = []
            positions = kundli_data.get("planetary_positions", [])

            ascendant_sign = None
            moon_sign = None
            planet_lines = []
            for p in positions:
                name = p.get("name", "Unknown")
                sign = p.get("sign_name", "")
                is_retro = str(p.get("isRetro", "")).lower() == "true"

                if name == "Ascendant":
                    ascendant_sign = sign
                    continue
                if name == "Moon":
                    moon_sign = sign

                retro_marker = " (retrograde)" if is_retro else ""
                planet_lines.append(f"{name} in {sign}{retro_marker}")

            if ascendant_sign:
                lines.append(f"Ascendant (Lagna): {ascendant_sign}")
            if moon_sign:
                lines.append(f"Moon Sign (Rashi): {moon_sign}")
            if planet_lines:
                lines.append("Planetary positions: " + ", ".join(planet_lines))

            chart_positions = kundli_data.get("chart_planet_positions", {})
            d9 = chart_positions.get("D9", {}) if chart_positions else {}
            d9_asc = d9.get("Ascendant", {}).get("sign_name") if d9 else None
            if d9_asc:
                lines.append(f"Navamsa (D9) Ascendant: {d9_asc}")

            if dasha_info and dasha_info.get("current_mahadasha", {}).get("lord"):
                maha = dasha_info["current_mahadasha"]
                antar = dasha_info.get("current_antardasha")
                praty = dasha_info.get("current_pratyantardasha")

                dasha_line = f"Current Dasha Period (REAL, from Dasha API — actual calendar dates): Mahadasha={maha['lord']}"
                if antar:
                    dasha_line += f", Antardasha={antar.get('lord')}"
                if praty:
                    dasha_line += f", Pratyantardasha={praty.get('lord')}"
                lines.append(dasha_line)
                if maha.get("start") and maha.get("end"):
                    lines.append(f"Current Mahadasha runs from {maha['start']} to {maha['end']}")
            else:
                lines.append(
                    "Current Dasha Period: NOT AVAILABLE right now. Do not state a specific "
                    "Mahadasha or Antardasha lord — speak about the chart placements instead."
                )

            ascendant_pred = kundli_data.get("ascendant_sign_prediction", "")
            if ascendant_pred:
                lines.append(f"Ascendant reading: {str(ascendant_pred)[:400]}")

            bhagyodaya = kundli_data.get("bhagyodaya", "")
            if bhagyodaya:
                lines.append(f"Prosperity period: {str(bhagyodaya)[:300]}")

            if not lines:
                logger.warning(f"summarize_kundli found nothing usable. Raw keys: {list(kundli_data.keys())}")
                return "No structured chart data available."
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Failed to summarize kundli data: {e}")
            return "No structured chart data available."

    def extract_chart_data(self, kundli_data: Dict) -> Optional[Dict]:
        """This is the SINGLE source of truth for planet/ascendant
        extraction. Call it fresh off kundli_full_raw every time you need
        verified chart facts — do not trust a separately cached copy that
        could drift from the raw API payload."""
        if not kundli_data:
            return None
        try:
            positions = kundli_data.get("planetary_positions", [])
            planets = []
            ascendant_sign = None
            for p in positions:
                name = p.get("name", "Unknown")
                sign = p.get("sign_name", "")
                is_retro = "true" if str(p.get("isRetro", "")).lower() == "true" else "false"
                if name == "Ascendant":
                    ascendant_sign = sign
                    continue
                planets.append({"name": name, "sign_name": sign, "isRetro": is_retro})
            return {"planets": planets, "ascendant_sign": ascendant_sign}
        except Exception as e:
            logger.error(f"Failed to extract chart data: {e}")
            return None

    def extract_divisional_chart(self, kundli_data: Dict, chart_code: str) -> Optional[Dict]:
        try:
            chart_positions = kundli_data.get("chart_planet_positions", {})
            chart = chart_positions.get(chart_code)
            if not chart:
                return None

            ascendant_sign = chart.get("Ascendant", {}).get("sign_name")
            planets = {}
            for planet_name, planet_data in chart.items():
                if planet_name == "Ascendant":
                    continue
                planets[planet_name] = planet_data.get("sign_name")

            return {"ascendant_sign": ascendant_sign, "planets": planets}
        except Exception as e:
            logger.error(f"Failed to extract {chart_code} chart: {e}")
            return None

    def summarize_divisional_chart(self, kundli_data: Dict, chart_code: str, purpose: str) -> str:
        chart = self.extract_divisional_chart(kundli_data, chart_code)
        if not chart or not chart.get("ascendant_sign"):
            return ""

        lines = [f"{chart_code} Chart (for {purpose}): Ascendant is {chart['ascendant_sign']}"]
        planet_strs = [f"{name} in {sign}" for name, sign in chart.get("planets", {}).items() if sign]
        if planet_strs:
            lines.append(", ".join(planet_strs))
        return " — ".join(lines)

    def get_moon_sign(self, kundli_data: Dict) -> Optional[str]:
        try:
            for p in kundli_data.get("planetary_positions", []):
                if p.get("name") == "Moon":
                    return p.get("sign_name")
        except Exception as e:
            logger.error(f"Failed to extract moon sign: {e}")
        return None

    def get_full_chart_bundle(self, kundli_data: Dict, dasha_info: Optional[Dict] = None) -> Dict:
        return {
            "summary": self.summarize_kundli(kundli_data, dasha_info=dasha_info),
            "chart": self.extract_chart_data(kundli_data),
            "dasha": dasha_info,
            "divisional": {
                "D9": self.extract_divisional_chart(kundli_data, "D9"),
                "D10": self.extract_divisional_chart(kundli_data, "D10"),
                "D24": self.extract_divisional_chart(kundli_data, "D24"),
            },
        }

   


kundli_service = KundliService()