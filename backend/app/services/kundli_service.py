import json
import urllib.request
import urllib.error
from typing import Optional, Dict
from app.utils.logger import logger

FUNCTION_URL = "https://vutgjzjv7ilckzs7ooeh5gnnyy0xnkdz.lambda-url.ap-south-1.on.aws/"

DASHA_SEQUENCE = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
DASHA_YEARS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17
}
NAKSHATRA_LORDS = (
    ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"] * 3
)

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


def calculate_vimshottari_dasha(moon_degree: float, moon_star_lord: str, moon_pada: int) -> Optional[Dict]:
    try:
        NAKSHATRA_ARC = 13.333333

        nakshatra_num = int(moon_degree / NAKSHATRA_ARC) + 1
        nakshatra_lord = NAKSHATRA_LORDS[nakshatra_num - 1]

        if nakshatra_lord != moon_star_lord:
            logger.warning(f"Dasha lord mismatch: calculated {nakshatra_lord} vs API {moon_star_lord} — using API value")
            nakshatra_lord = moon_star_lord

        position_in_nakshatra = moon_degree % NAKSHATRA_ARC
        fraction_passed = position_in_nakshatra / NAKSHATRA_ARC

        start_lord_idx = DASHA_SEQUENCE.index(nakshatra_lord)
        start_dasha_years = DASHA_YEARS[nakshatra_lord]
        balance_years = start_dasha_years * (1 - fraction_passed)

        dasha_timeline = []
        current_year = 0.0
        for i in range(9):
            lord_idx = (start_lord_idx + i) % 9
            lord = DASHA_SEQUENCE[lord_idx]
            years = balance_years if i == 0 else DASHA_YEARS[lord]

            dasha_timeline.append({
                "lord": lord,
                "years": round(years, 2),
                "start_year": round(current_year, 2),
                "end_year": round(current_year + years, 2),
            })
            current_year += years

        return {
            "birth_nakshatra": nakshatra_num,
            "nakshatra_lord": nakshatra_lord,
            "moon_pada": moon_pada,
            "balance_of_dasha_at_birth": round(balance_years, 2),
            "dasha_sequence": dasha_timeline,
            "current_mahadasha": dasha_timeline[0],
        }
    except Exception as e:
        logger.error(f"Dasha calculation failed: {e}")
        return None


def calculate_full_dasha_periods(moon_degree: float, moon_star_lord: str, moon_pada: int) -> Optional[Dict]:
    mahadasha_info = calculate_vimshottari_dasha(moon_degree, moon_star_lord, moon_pada)
    if not mahadasha_info:
        return None

    try:
        current_maha = mahadasha_info["current_mahadasha"]
        maha_lord = current_maha["lord"]
        maha_start_year = current_maha["start_year"]
        maha_total_years = DASHA_YEARS[maha_lord]
        maha_lord_idx = DASHA_SEQUENCE.index(maha_lord)

        antardasha_sequence = []
        elapsed = maha_start_year
        for i in range(9):
            antar_lord_idx = (maha_lord_idx + i) % 9
            antar_lord = DASHA_SEQUENCE[antar_lord_idx]
            antar_years = (maha_total_years * DASHA_YEARS[antar_lord]) / 120
            antardasha_sequence.append({
                "lord": antar_lord,
                "years": round(antar_years, 3),
                "start_year": round(elapsed, 3),
                "end_year": round(elapsed + antar_years, 3),
            })
            elapsed += antar_years

        mahadasha_info["antardasha_sequence"] = antardasha_sequence
        mahadasha_info["current_antardasha"] = antardasha_sequence[0]

        first_antar = antardasha_sequence[0]
        antar_lord = first_antar["lord"]
        antar_total_years = first_antar["years"]
        antar_lord_idx2 = DASHA_SEQUENCE.index(antar_lord)

        pratyantar_sequence = []
        elapsed2 = first_antar["start_year"]
        for i in range(9):
            praty_lord_idx = (antar_lord_idx2 + i) % 9
            praty_lord = DASHA_SEQUENCE[praty_lord_idx]
            praty_years = (antar_total_years * DASHA_YEARS[praty_lord]) / 120
            pratyantar_sequence.append({
                "lord": praty_lord,
                "years": round(praty_years, 4),
                "start_year": round(elapsed2, 4),
                "end_year": round(elapsed2 + praty_years, 4),
            })
            elapsed2 += praty_years

        mahadasha_info["pratyantardasha_sequence"] = pratyantar_sequence
        mahadasha_info["current_pratyantardasha"] = pratyantar_sequence[0]

        return mahadasha_info
    except Exception as e:
        logger.error(f"Antardasha/Pratyantardasha calculation failed: {e}")
        return mahadasha_info


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

    def _get_dasha_for_kundli(self, kundli_data: Dict) -> Optional[Dict]:
        try:
            moon_lord_data = kundli_data.get("planet_lords", {}).get("Moon", {})
            moon_degree = moon_lord_data.get("degree")
            moon_star_lord = moon_lord_data.get("star_lord")
            moon_pada = moon_lord_data.get("pada")

            if moon_degree is None or not moon_star_lord or moon_pada is None:
                logger.warning("Missing Moon degree/star_lord/pada — cannot calculate dasha")
                return None

            return calculate_full_dasha_periods(float(moon_degree), moon_star_lord, int(moon_pada))
        except Exception as e:
            logger.error(f"Failed to derive dasha inputs: {e}")
            return None

    def summarize_kundli(self, kundli_data: Dict, dob: Optional[str] = None) -> str:
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

            dasha_info = self._get_dasha_for_kundli(kundli_data)
            if dasha_info:
                maha = dasha_info["current_mahadasha"]
                antar = dasha_info.get("current_antardasha")
                praty = dasha_info.get("current_pratyantardasha")

                dasha_line = f"Current Dasha Period (approximate, calculated): Mahadasha={maha['lord']}"
                if antar:
                    dasha_line += f", Antardasha={antar['lord']}"
                if praty:
                    dasha_line += f", Pratyantardasha={praty['lord']}"
                lines.append(dasha_line)

                if len(dasha_info["dasha_sequence"]) > 1:
                    nxt = dasha_info["dasha_sequence"][1]
                    if dob:
                        try:
                            from datetime import datetime as _dt
                            birth_year = _dt.strptime(dob.strip(), "%d-%m-%Y").year
                            approx_year = birth_year + int(nxt["start_year"])
                            lines.append(f"Next Mahadasha: {nxt['lord']} (approx. begins around {approx_year})")
                        except (ValueError, TypeError):
                            pass

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

    def get_full_chart_bundle(self, kundli_data: Dict) -> Dict:
        return {
            "summary": self.summarize_kundli(kundli_data),
            "chart": self.extract_chart_data(kundli_data),
            "dasha": self._get_dasha_for_kundli(kundli_data),
            "divisional": {
                "D9": self.extract_divisional_chart(kundli_data, "D9"),
                "D10": self.extract_divisional_chart(kundli_data, "D10"),
                "D24": self.extract_divisional_chart(kundli_data, "D24"),
            },
        }

    def get_real_or_calculated_dasha(self, kundli_data: Dict, dob: str, birth_time_24h: str,
                                       latitude: float, longitude: float) -> Optional[Dict]:
        """Try the REAL dasha API first (actual calendar dates, authoritative).
        Falls back to the hand-calculated Vimshottari math only if the real
        API is unavailable, misconfigured, or missing required data."""
        from app.services.dasha_api_service import dasha_api_service

        try:
            ascendant_data = self.get_ascendant_data(kundli_data)
            if not ascendant_data:
                logger.warning("No ascendant_data available — skipping real dasha API, using calculated fallback")
            elif dob:
                # dob is already DD-MM-YYYY — exactly what this Lambda's
                # dateOfBirth field expects. DO NOT convert to slashes here;
                # that was the bug that caused this to silently fail before.
                dasha_tree = dasha_api_service.fetch_dasha_tree(
                    date=dob, time=birth_time_24h,
                    latitude=latitude, longitude=longitude,
                    ascendant_data=ascendant_data,
                )
                if dasha_tree:
                    current_period = dasha_api_service.find_current_period(dasha_tree)
                    if current_period:
                        logger.info("Using REAL dasha API data (with actual calendar dates)")
                        return current_period
        except Exception as e:
            logger.warning(f"Real dasha API failed, falling back to calculated dasha: {e}")

        logger.info("Falling back to calculated Vimshottari dasha (years-from-birth)")
        return self._get_dasha_for_kundli(kundli_data)

kundli_service = KundliService()