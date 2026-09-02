import json
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional, Dict, List

from app.utils.logger import logger

DATE_FORMAT = "%d/%m/%Y %H:%M:%S"

DASHA_LAMBDA_URL = "https://bivrov2febq5ued37psv2hcxyi0wlxet.lambda-url.ap-south-1.on.aws/"
DASHA_LAMBDA_BEARER_TOKEN = "f83c6105-1731-4cd9-9d94-9543ff01bfe1"

# Confirmed-working Dasha API requirement.
# No Vimshottari/local calculation fallback.
REQUIREMENT = "Dasha"

# Generic response keys are kept only as parser fallbacks.
GENERIC_LIST_KEYS = ("mahadasha", "dasha", "vimshottari", "data", "result")


def _profile(label: str, start: float):
    elapsed = time.perf_counter() - start
    logger.info(f"[Profile][DashaAPI] {label}: {elapsed:.3f}s")
    return elapsed


def _parse_dt(date_str: str) -> Optional[datetime]:
    try:
        return datetime.strptime(date_str, DATE_FORMAT)
    except (ValueError, TypeError):
        return None


def _extract_list_from_response(
    response,
    requirement: str
) -> Optional[List[Dict]]:
    """
    Extract Dasha data from the API response.

    The confirmed API response format is:

        {"Dasha": [...]}

    The requirement key is matched case-insensitively.
    """

    if isinstance(response, list):
        return response

    if not isinstance(response, dict):
        logger.warning(
            f"Dasha API returned unexpected response type: "
            f"{type(response).__name__}"
        )
        return None

    # Match the actual requirement key case-insensitively.
    # Example: "Dasha" == "dasha"
    lower_map = {
        str(key).lower(): key
        for key in response.keys()
    }

    match_key = lower_map.get(requirement.lower())

    if match_key is not None:
        value = response[match_key]

        if isinstance(value, list):
            logger.info(
                f"Dasha API response parsed successfully via key '{match_key}'"
            )
            return value

        logger.warning(
            f"Dasha API key '{match_key}' exists but value is "
            f"{type(value).__name__}, not a list"
        )

    # Generic parser fallback.
    # These are response keys only, NOT alternative API requirements.
    for key in GENERIC_LIST_KEYS:
        actual_key = lower_map.get(key.lower())

        if actual_key is not None:
            value = response[actual_key]

            if isinstance(value, list):
                logger.info(
                    f"Dasha API response parsed successfully via key '{actual_key}'"
                )
                return value

    logger.warning(
        f"Dasha API returned unexpected keys "
        f"(requirement={requirement!r}): {list(response.keys())}"
    )

    return None


class DashaApiService:

    def _try_fetch(
        self,
        payload: Dict,
        max_retries: int
    ) -> Optional[List[Dict]]:

        req = urllib.request.Request(
            DASHA_LAMBDA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DASHA_LAMBDA_BEARER_TOKEN}",
            },
            method="POST",
        )

        requirements = payload.get("requirements", [])

        for attempt in range(1, max_retries + 2):

            t0 = time.perf_counter()

            try:
                with urllib.request.urlopen(
                    req,
                    timeout=45
                ) as resp:
                    response = json.loads(
                        resp.read().decode("utf-8")
                    )

                _profile(
                    f"HTTP call "
                    f"(requirements={requirements}, attempt {attempt})",
                    t0
                )

                result = _extract_list_from_response(
                    response,
                    REQUIREMENT
                )

                if result is not None:
                    return result

                # HTTP request succeeded but response structure
                # did not contain usable Dasha data.
                return None

            except urllib.error.HTTPError as e:

                _profile(
                    f"HTTP call FAILED {e.code} (attempt {attempt})",
                    t0
                )

                try:
                    error_body = e.read().decode("utf-8")
                except Exception:
                    error_body = "<unable to read error body>"

                # Do not retry client-side errors.
                if 400 <= e.code < 500:
                    logger.warning(
                        f"Dasha API rejected "
                        f"requirements={requirements!r} "
                        f"(HTTP {e.code}): {error_body}"
                    )
                    return None

                logger.warning(
                    f"Dasha API HTTP error {e.code} on attempt {attempt} "
                    f"(requirements={requirements}): {error_body}"
                )

            except Exception as e:

                _profile(
                    f"HTTP call ERRORED (attempt {attempt})",
                    t0
                )

                logger.warning(
                    f"Dasha API request failed on attempt {attempt} "
                    f"(requirements={requirements}): {e}"
                )

        logger.error(
            f"Dasha API fetch failed after {max_retries + 1} attempts "
            f"(requirements={requirements})"
        )

        return None

    def fetch_dasha_tree(
        self,
        date: str,
        birth_time: str,
        latitude: float,
        longitude: float,
        ascendant_data: Dict,
        timezone_name: str = "Asia/Kolkata",
        language: str = "english",
        max_retries: int = 2,
    ) -> Optional[List[Dict]]:

        t_total = time.perf_counter()

        payload = {
            "requirements": [REQUIREMENT],
            "dateOfBirth": date,
            "time_of_birth": birth_time,
            "latitude": str(latitude),
            "longitude": str(longitude),
            "timezone_name": timezone_name,
            "language": language,
            "ascendant_data": ascendant_data,
        }

        result = self._try_fetch(
            payload,
            max_retries
        )

        _profile(
            "fetch_dasha_tree TOTAL",
            t_total
        )

        if result is not None:
            logger.info(
                "Dasha API succeeded with "
                f"requirements=['{REQUIREMENT}']"
            )
        else:
            logger.error(
                "Dasha API failed for "
                f"requirements=['{REQUIREMENT}']"
            )

        return result

    def flatten_periods(
        self,
        dasha_tree: List[Dict],
        level: str = "antardasha"
    ) -> List[Dict]:

        flat = []

        for maha in dasha_tree:

            maha_lord = (
                maha.get("mahadasha")
                or maha.get("mahadasha_display")
            )

            if level == "mahadasha":

                flat.append({
                    "mahadasha": maha_lord,
                    "antardasha": None,
                    "start": maha.get("start"),
                    "end": maha.get("end"),
                })

                continue

            for antar in maha.get("antardasha", []):

                antar_lord = (
                    antar.get("antardasha")
                    or antar.get("antardasha_display")
                )

                flat.append({
                    "mahadasha": maha_lord,
                    "antardasha": antar_lord,
                    "start": antar.get("start"),
                    "end": antar.get("end"),
                })

        return flat

    def get_upcoming_periods(
        self,
        dasha_tree: List[Dict],
        months_ahead: int = 60
    ) -> List[Dict]:

        now = datetime.now()

        cutoff = now.replace(
            year=now.year + (months_ahead // 12)
        )

        all_periods = self.flatten_periods(
            dasha_tree,
            level="antardasha"
        )

        upcoming = []

        for period in all_periods:

            end = _parse_dt(
                period.get("end", "")
            )

            start = _parse_dt(
                period.get("start", "")
            )

            if not start or not end:
                continue

            if end < now:
                continue

            if start > cutoff:
                break

            upcoming.append(period)

        return upcoming

    def find_current_period(
        self,
        dasha_tree: List[Dict]
    ) -> Optional[Dict]:

        now = datetime.now()

        current_maha = None

        for maha in dasha_tree:

            maha_start = _parse_dt(
                maha.get("start", "")
            )

            maha_end = _parse_dt(
                maha.get("end", "")
            )

            if (
                maha_start
                and maha_end
                and maha_start <= now <= maha_end
            ):
                current_maha = maha
                break

        if not current_maha:
            logger.warning(
                "Could not find a Mahadasha period "
                "containing the current date"
            )
            return None

        current_antar = None

        for antar in current_maha.get(
            "antardasha",
            []
        ):

            antar_start = _parse_dt(
                antar.get("start", "")
            )

            antar_end = _parse_dt(
                antar.get("end", "")
            )

            if (
                antar_start
                and antar_end
                and antar_start <= now <= antar_end
            ):
                current_antar = antar
                break

        current_praty = None

        if current_antar:

            for praty in current_antar.get(
                "pratyantar",
                []
            ):

                praty_start = _parse_dt(
                    praty.get("start", "")
                )

                praty_end = _parse_dt(
                    praty.get("end", "")
                )

                if (
                    praty_start
                    and praty_end
                    and praty_start <= now <= praty_end
                ):
                    current_praty = praty
                    break

        result = {
            "current_mahadasha": {
                "lord": (
                    current_maha.get("mahadasha")
                    or current_maha.get("mahadasha_display")
                ),
                "start": current_maha.get("start"),
                "end": current_maha.get("end"),
            }
        }

        if current_antar:

            result["current_antardasha"] = {
                "lord": (
                    current_antar.get("antardasha")
                    or current_antar.get("antardasha_display")
                ),
                "start": current_antar.get("start"),
                "end": current_antar.get("end"),
            }

        if current_praty:

            result["current_pratyantardasha"] = {
                "lord": (
                    current_praty.get("pratyantar")
                    or current_praty.get("pratyantar_display")
                ),
                "start": current_praty.get("start"),
                "end": current_praty.get("end"),
            }

        return result


dasha_api_service = DashaApiService()