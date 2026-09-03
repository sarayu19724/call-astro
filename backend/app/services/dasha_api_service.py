import json
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional, Dict, List, Tuple

from app.utils.logger import logger

DATE_FORMAT = "%d/%m/%Y %H:%M:%S"

import os

DASHA_LAMBDA_URL = "https://bivrov2febq5ued37psv2hcxyi0wlxet.lambda-url.ap-south-1.on.aws/"
DASHA_LAMBDA_BEARER_TOKEN = os.environ.get("DASHA_LAMBDA_BEARER_TOKEN", "f83c6105-1731-4cd9-9d94-9543ff01bfe1")

FEATURE = "Mahadasha"


def _parse_dt(date_str: str) -> Optional[datetime]:
    try:
        return datetime.strptime(date_str, DATE_FORMAT)
    except (ValueError, TypeError):
        return None


class DashaApiService:
    def fetch_dasha_tree(
        self,
        date: str,
        time: str,
        latitude: float,
        longitude: float,
        ascendant_data: Dict,
        timezone_name: str = "Asia/Kolkata",
        language: str = "english",
        max_retries: int = 2,
    ) -> Optional[List[Dict]]:
        payload = {
            "requirements": [FEATURE],
            "dateOfBirth": date,
            "time_of_birth": time,
            "latitude": str(latitude),
            "longitude": str(longitude),
            "timezone_name": timezone_name,
            "language": language,
            "ascendant_data": ascendant_data,
        }    
        
        req = urllib.request.Request(
            DASHA_LAMBDA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DASHA_LAMBDA_BEARER_TOKEN}",
            },
            method="POST",
        )
        logger.info(f"Dasha API payload being sent: {json.dumps(payload, default=str)}")
        for attempt in range(1, max_retries + 2):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    response = json.loads(resp.read().decode("utf-8"))

                logger.info(f"Dasha API response fetched successfully (attempt {attempt})")

                if isinstance(response, dict) and "body" in response:
                    body_value = response["body"]
                    response = json.loads(body_value) if isinstance(body_value, str) else body_value
                
                if isinstance(response, list):
                    return response

                if isinstance(response, dict) and FEATURE in response:
                    feature_value = response[FEATURE]
                    if isinstance(feature_value, str):
                        try:
                            feature_value = json.loads(feature_value)
                        except json.JSONDecodeError:
                            logger.error(f"Dasha API '{FEATURE}' value was an unparseable string: {str(feature_value)[:200]}")
                            return None
                    if isinstance(feature_value, list):
                        return feature_value
                    logger.warning(f"Dasha API '{FEATURE}' value has unexpected type: {type(feature_value)}")
                    return None

                logger.warning(f"Dasha API returned unexpected shape: {type(response)}")
                return None
                
            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8")
                if 400 <= e.code < 500:
                    logger.error(f"Dasha API rejected request (HTTP {e.code}): {error_body}")
                    return None
                logger.warning(f"Dasha API HTTP error {e.code} on attempt {attempt}: {error_body}")

            except Exception as e:
                logger.warning(f"Dasha API request failed on attempt {attempt}: {e}")

        logger.error(f"Dasha API fetch failed after {max_retries + 1} attempts")
        return None

    def find_current_period(self, dasha_tree: List[Dict]) -> Optional[Dict]:
        now = datetime.now()

        current_maha = None
        for maha in dasha_tree:
            maha_start = _parse_dt(maha.get("start", ""))
            maha_end = _parse_dt(maha.get("end", ""))
            if maha_start and maha_end and maha_start <= now <= maha_end:
                current_maha = maha
                break

        if not current_maha:
            logger.warning("Could not find a Mahadasha period containing the current date")
            return None

        current_antar = None
        for antar in current_maha.get("antardashas", []):
            antar_start = _parse_dt(antar.get("start", ""))
            antar_end = _parse_dt(antar.get("end", ""))
            if antar_start and antar_end and antar_start <= now <= antar_end:
                current_antar = antar
                break

        current_praty = None
        if current_antar:
            for praty in current_antar.get("pratyantar", []):
                praty_start = _parse_dt(praty.get("start", ""))
                praty_end = _parse_dt(praty.get("end", ""))
                if praty_start and praty_end and praty_start <= now <= praty_end:
                    current_praty = praty
                    break

        result = {
            "current_mahadasha": {
                "lord": current_maha.get("mahadasha") or current_maha.get("mahadasha_display"),
                "start": current_maha.get("start"),
                "end": current_maha.get("end"),
            }
        }
        if current_antar:
            result["current_antardasha"] = {
                "lord": current_antar.get("antardasha") or current_antar.get("antardasha_display"),
                "start": current_antar.get("start"),
                "end": current_antar.get("end"),
            }
        if current_praty:
            result["current_pratyantardasha"] = {
                "lord": current_praty.get("pratyantar") or current_praty.get("pratyantar_display"),
                "start": current_praty.get("start"),
                "end": current_praty.get("end"),
            }

        return result

    def fetch_tree_and_current_period(
        self,
        date: str,
        time: str,
        latitude: float,
        longitude: float,
        ascendant_data: Dict,
        timezone_name: str = "Asia/Kolkata",
        language: str = "english",
    ) -> Tuple[Optional[List[Dict]], Optional[Dict]]:
        """PERFORMANCE FIX: single external API call that returns BOTH the
        full Dasha tree AND the derived current period, so callers never
        need to hit the Dasha Lambda twice for the same birth data — once
        for 'what's the current period' and again for 'give me the full
        upcoming timeline'. Both come from this one fetch. Returns
        (tree, current_period) — either half may be None on failure."""
        tree = self.fetch_dasha_tree(
            date=date, time=time, latitude=latitude, longitude=longitude,
            ascendant_data=ascendant_data, timezone_name=timezone_name, language=language,
        )
        if not tree:
            return None, None
        current_period = self.find_current_period(tree)
        return tree, current_period

    def flatten_periods(self, dasha_tree: List[Dict], level: str = "antardasha") -> List[Dict]:
        flat = []
        for maha in dasha_tree:
            maha_lord = maha.get("mahadasha") or maha.get("mahadasha_display")
            if level == "mahadasha":
                flat.append({
                    "mahadasha": maha_lord,
                    "antardasha": None,
                    "start": maha.get("start"),
                    "end": maha.get("end"),
                })
                continue
            for antar in maha.get("antardashas", []):
                antar_lord = antar.get("antardasha") or antar.get("antardasha_display")
                flat.append({
                    "mahadasha": maha_lord,
                    "antardasha": antar_lord,
                    "start": antar.get("start"),
                    "end": antar.get("end"),
                })
        return flat

    def get_upcoming_periods(self, dasha_tree: List[Dict], months_ahead: int = 60) -> List[Dict]:
        now = datetime.now()
        cutoff = now.replace(year=now.year + (months_ahead // 12))

        all_periods = self.flatten_periods(dasha_tree, level="antardasha")
        upcoming = []
        for period in all_periods:
            end = _parse_dt(period.get("end", ""))
            start = _parse_dt(period.get("start", ""))
            if not start or not end:
                continue
            if end < now:
                continue
            if start > cutoff:
                break
            upcoming.append(period)
        return upcoming


dasha_api_service = DashaApiService()