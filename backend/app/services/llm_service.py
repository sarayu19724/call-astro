import json
import requests
import re
from datetime import datetime
from typing import Dict, Any, Optional
from app.config.settings import settings
from app.utils.logger import logger


try:
    from dateutil import parser as dateutil_parser
    DATEUTIL_AVAILABLE = True
except ImportError:
    DATEUTIL_AVAILABLE = False
    logger.warning(
        "python-dateutil not installed — falling back to regex-only date parsing. "
        "Run: pip install python-dateutil"
    )


class LLMService:

    def __init__(self):
        # ============================================================
        # LOCAL OLLAMA
        # ============================================================
        self.host = settings.OLLAMA_HOST
        self.model = settings.OLLAMA_LLM_MODEL

        # ============================================================
        # OLLAMA CLOUD
        # ============================================================
        self.api_key = getattr(settings, "OLLAMA_API_KEY", None)
        self.cloud_model = getattr(
            settings,
            "OLLAMA_CLOUD_MODEL",
            "gpt-oss:20b"
        )
        self.cloud_url = "https://ollama.com/api"

        if self.api_key:
            logger.info(
                f"LLM Service initialised using Ollama Cloud, "
                f"model: {self.cloud_model}"
            )
        else:
            logger.info(
                f"LLM Service initialised using local Ollama host: "
                f"{self.host}, model: {self.model}"
            )

    # ================================================================
    # GENERATE — LOCAL OLLAMA OR OLLAMA CLOUD
    # ================================================================
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_format: bool = False,
        temperature: float = 0.3
    ) -> str:

        try:

            # ========================================================
            # OLLAMA CLOUD
            # ========================================================
            if self.api_key:

                url = f"{self.cloud_url}/chat"

                messages = []

                if system_prompt:
                    messages.append({
                        "role": "system",
                        "content": system_prompt
                    })

                messages.append({
                    "role": "user",
                    "content": prompt
                })

                payload = {
                    "model": self.cloud_model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature
                    }
                }

                if json_format:
                    payload["format"] = "json"

                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }

                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=180
                )

                if response.status_code != 200:
                    logger.error(
                        f"Ollama Cloud returned status "
                        f"{response.status_code}: {response.text}"
                    )
                    raise RuntimeError(
                        f"Ollama Cloud error "
                        f"({response.status_code}): {response.text}"
                    )

                result = response.json()

                return (
                    result
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )

            # ========================================================
            # LOCAL OLLAMA
            # ========================================================
            url = f"{self.host.rstrip('/')}/api/generate"

            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature
                }
            }

            if system_prompt:
                payload["system"] = system_prompt

            if json_format:
                payload["format"] = "json"

            response = requests.post(
                url,
                json=payload,
                timeout=120
            )

            if response.status_code == 200:
                result = response.json()
                return result.get("response", "").strip()

            elif response.status_code == 404:
                logger.error(
                    f"Ollama returned 404: "
                    f"Model '{self.model}' not found."
                )
                raise RuntimeError(
                    f"Ollama model '{self.model}' is not pulled or running. "
                    f"Run: ollama pull {self.model}"
                )

            else:
                logger.error(
                    f"Ollama returned status code "
                    f"{response.status_code}: {response.text}"
                )
                raise RuntimeError(
                    f"Ollama server error "
                    f"({response.status_code}): {response.text}"
                )

        except requests.exceptions.ConnectionError as ce:

            if self.api_key:
                logger.error(
                    "Failed to connect to Ollama Cloud."
                )
                raise RuntimeError(
                    "Cannot connect to Ollama Cloud."
                ) from ce

            logger.error(
                f"Failed to connect to Ollama server at {self.host}."
            )
            raise RuntimeError(
                f"Cannot connect to Ollama server at {self.host}."
            ) from ce

        except Exception as e:
            logger.error(
                f"Error communicating with Ollama LLM: {e}"
            )
            raise

    # ================================================================
    # STREAMING — LOCAL OLLAMA OR OLLAMA CLOUD
    # ================================================================
    def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.6
    ):

        try:

            # ========================================================
            # OLLAMA CLOUD STREAMING
            # ========================================================
            if self.api_key:

                url = f"{self.cloud_url}/chat"

                payload = {
                    "model": self.cloud_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "stream": True,
                    "options": {
                        "temperature": temperature
                    }
                }

                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }

                with requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=180,
                    stream=True
                ) as response:

                    if response.status_code != 200:
                        error_text = response.text

                        logger.error(
                            f"Ollama Cloud stream returned "
                            f"status {response.status_code}: "
                            f"{error_text}"
                        )

                        raise RuntimeError(
                            f"Ollama Cloud error "
                            f"({response.status_code})"
                        )

                    for line in response.iter_lines():

                        if not line:
                            continue

                        try:
                            data = json.loads(
                                line.decode("utf-8")
                            )
                        except json.JSONDecodeError:
                            continue

                        token = (
                            data
                            .get("message", {})
                            .get("content", "")
                        )

                        if token:
                            yield token

                        if data.get("done"):
                            break

                return

            # ========================================================
            # LOCAL OLLAMA STREAMING
            # ========================================================
            url = f"{self.host.rstrip('/')}/api/generate"

            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "temperature": temperature
                }
            }

            with requests.post(
                url,
                json=payload,
                timeout=120,
                stream=True
            ) as response:

                if response.status_code != 200:
                    logger.error(
                        f"Ollama stream returned status "
                        f"{response.status_code}: {response.text}"
                    )
                    raise RuntimeError(
                        f"Ollama server error "
                        f"({response.status_code})"
                    )

                for line in response.iter_lines():

                    if not line:
                        continue

                    try:
                        data = json.loads(
                            line.decode("utf-8")
                        )
                    except json.JSONDecodeError:
                        continue

                    token = data.get("response", "")

                    if token:
                        yield token

                    if data.get("done"):
                        break

        except requests.exceptions.ConnectionError as ce:

            if self.api_key:
                logger.error(
                    "Failed to connect to Ollama Cloud."
                )
                raise RuntimeError(
                    "Cannot connect to Ollama Cloud."
                ) from ce

            logger.error(
                f"Failed to connect to Ollama server at {self.host}."
            )
            raise RuntimeError(
                f"Cannot connect to Ollama server at {self.host}."
            ) from ce

        except Exception as e:
            logger.error(
                f"Error during Ollama stream: {e}"
            )
            raise

    # ================================================================
    # DATE EXTRACTION
    # ================================================================
    def _extract_date_regex(
        self,
        text: str
    ) -> Optional[str]:

        if DATEUTIL_AVAILABLE:

            try:
                parsed = dateutil_parser.parse(
                    text,
                    fuzzy=True,
                    dayfirst=True
                )

                current_year = datetime.now().year

                if 1900 <= parsed.year <= current_year:

                    dob = parsed.strftime(
                        "%d-%m-%Y"
                    )

                    logger.info(
                        f"Extracted date via dateutil: {dob}"
                    )

                    return dob

            except (ValueError, OverflowError):
                pass

        text_lower = text.lower()

        months = {
            'january': '01',
            'jan': '01',
            'जनवरी': '01',

            'february': '02',
            'feb': '02',
            'फरवरी': '02',

            'march': '03',
            'mar': '03',
            'मार्च': '03',

            'april': '04',
            'apr': '04',
            'अप्रैल': '04',

            'may': '05',
            'मई': '05',

            'june': '06',
            'jun': '06',
            'जून': '06',

            'july': '07',
            'jul': '07',
            'जुलाई': '07',

            'august': '08',
            'aug': '08',
            'अगस्त': '08',

            'september': '09',
            'sep': '09',
            'सितंबर': '09',

            'october': '10',
            'oct': '10',
            'अक्टूबर': '10',

            'november': '11',
            'nov': '11',
            'नवंबर': '11',

            'december': '12',
            'dec': '12',
            'दिसंबर': '12'
        }

        pattern1 = (
            r'(\d{1,2})\s*[-/.]?\s*'
            r'(january|february|march|april|may|june|july|'
            r'august|september|october|november|december|'
            r'जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|'
            r'सितंबर|अक्टूबर|नवंबर|दिसंबर|jan|feb|mar|apr|'
            r'may|jun|jul|aug|sep|oct|nov|dec)'
            r'\s*[-/.]?\s*(\d{4})'
        )

        match = re.search(
            pattern1,
            text_lower
        )

        if match:

            day, month_name, year = match.groups()

            month_num = months.get(
                month_name.lower(),
                '00'
            )

            return (
                f"{day.zfill(2)}-"
                f"{month_num}-"
                f"{year}"
            )

        pattern2 = (
            r'(january|february|march|april|may|june|july|'
            r'august|september|october|november|december|'
            r'जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|'
            r'सितंबर|अक्टूबर|नवंबर|दिसंबर|jan|feb|mar|apr|'
            r'may|jun|jul|aug|sep|oct|nov|dec)'
            r'\s+(\d{1,2})\s*[-,.]?\s*(\d{4})'
        )

        match = re.search(
            pattern2,
            text_lower
        )

        if match:

            month_name, day, year = match.groups()

            month_num = months.get(
                month_name.lower(),
                '00'
            )

            return (
                f"{day.zfill(2)}-"
                f"{month_num}-"
                f"{year}"
            )

        pattern3 = (
            r'(\d{1,2})\s*[-/]\s*'
            r'(\d{1,2})\s*[-/]\s*(\d{4})'
        )

        match = re.search(
            pattern3,
            text_lower
        )

        if match:

            day, month, year = match.groups()

            return (
                f"{day.zfill(2)}-"
                f"{month.zfill(2)}-"
                f"{year}"
            )

        pattern4 = (
            r'(\d{4})\s*[-/]\s*'
            r'(\d{1,2})\s*[-/]\s*(\d{1,2})'
        )

        match = re.search(
            pattern4,
            text_lower
        )

        if match:

            year, month, day = match.groups()

            return (
                f"{day.zfill(2)}-"
                f"{month.zfill(2)}-"
                f"{year}"
            )

        return None

    # ================================================================
    # TIME EXTRACTION
    # ================================================================
    def _extract_time_regex(
        self,
        text: str
    ) -> Optional[str]:

        if DATEUTIL_AVAILABLE and re.search(
            r'\d',
            text
        ):

            try:

                parsed = dateutil_parser.parse(
                    text,
                    fuzzy=True
                )

                if re.search(
                    r'\d{1,2}\s*[:.]?\s*\d{0,2}\s*(am|pm|AM|PM)?',
                    text
                ):

                    time_str = parsed.strftime(
                        "%I:%M %p"
                    ).lstrip("0")

                    logger.info(
                        f"Extracted time via dateutil: {time_str}"
                    )

                    return time_str

            except (ValueError, OverflowError):
                pass

        text_lower = text.lower()

        pattern1 = (
            r'(\d{1,2})\s*[:.]?\s*'
            r'(\d{2})\s*(am|pm|AM|PM)'
        )

        match = re.search(
            pattern1,
            text_lower
        )

        if match:

            hour, minute, period = match.groups()

            return (
                f"{hour}:{minute} "
                f"{period.upper()}"
            )

        pattern2 = (
            r'(\d{1,2})\s*(am|pm|AM|PM)'
        )

        match = re.search(
            pattern2,
            text_lower
        )

        if match:

            hour, period = match.groups()

            return (
                f"{hour}:00 "
                f"{period.upper()}"
            )

        return None

    # ================================================================
    # PLACE EXTRACTION
    # ================================================================
    def _extract_place_regex(
        self,
        text: str
    ) -> Optional[str]:

        text_lower = text.lower()

        patterns = [

            r'place\s*(?:is|:)\s*'
            r'([A-Za-z\s]+?)(?:\.|,|$)',

            r'born\s+in\s*'
            r'([A-Za-z\s]+?)(?:\.|,|$)',

            r'से\s+'
            r'([A-Za-z\s०-९]+?)(?:\.|,|$)',

            r'जगह\s*(?:है|:)\s*'
            r'([A-Za-z\s०-९]+?)(?:\.|,|$)'
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text_lower
            )

            if match:

                place = match.group(1).strip()

                if place and len(place) > 1:
                    return place

        return None

    # ================================================================
    # PROFILE EXTRACTION
    # ================================================================
    def extract_profile_details(
        self,
        message: str,
        history: str
    ) -> Dict[str, Any]:

        from app.prompts.templates import EXTRACTION_PROMPT

        result = {
            "dob": None,
            "birth_time": None,
            "birth_place": None,
            "language": "Hinglish",
            "is_astrology_query": True
        }

        prompt = EXTRACTION_PROMPT.format(
            history=history,
            message=message
        )

        try:

            raw_response = self.generate(
                prompt=prompt,
                json_format=True,
                temperature=0.0
            )

            cleaned = raw_response.strip()

            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]

            if cleaned.startswith("```"):
                cleaned = cleaned[3:]

            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]

            cleaned = cleaned.strip()

            try:

                parsed = json.loads(cleaned)

                if isinstance(parsed, dict):

                    if parsed.get("dob") not in [
                        "null",
                        "",
                        None,
                        "N/A"
                    ]:
                        result["dob"] = parsed.get("dob")

                    if parsed.get("birth_time") not in [
                        "null",
                        "",
                        None,
                        "N/A"
                    ]:
                        result["birth_time"] = parsed.get(
                            "birth_time"
                        )

                    if parsed.get("birth_place") not in [
                        "null",
                        "",
                        None,
                        "N/A"
                    ]:
                        result["birth_place"] = parsed.get(
                            "birth_place"
                        )

                    if parsed.get("language"):
                        result["language"] = parsed.get(
                            "language"
                        )

                    if "is_astrology_query" in parsed:
                        result["is_astrology_query"] = bool(
                            parsed.get(
                                "is_astrology_query",
                                True
                            )
                        )

            except json.JSONDecodeError:
                logger.debug(
                    "LLM JSON parsing failed, "
                    "using regex fallback"
                )

        except Exception as llm_err:

            logger.debug(
                f"LLM extraction failed: {llm_err}, "
                f"using regex fallback"
            )

        # Regex fallback searches ONLY the current message
        # (avoids extracting stale/fake data from the bot's own past replies)

        if not result["dob"]:

            extracted_dob = self._extract_date_regex(
                message
            )

            if extracted_dob:
                result["dob"] = extracted_dob

        if not result["birth_time"]:

            extracted_time = self._extract_time_regex(
                message
            )

            if extracted_time:
                result["birth_time"] = extracted_time

        if not result["birth_place"]:

            extracted_place = self._extract_place_regex(
                message
            )

            if extracted_place:
                result["birth_place"] = extracted_place

        logger.info(
            f"Final extracted profile: "
            f"dob={result['dob']}, "
            f"time={result['birth_time']}, "
            f"place={result['birth_place']}"
        )

        return result

    # ================================================================
    # FOLLOW-UP QUESTIONS
    # ================================================================
    def generate_followups(
        self,
        response_text: str,
        language: str
    ) -> list[str]:

        prompt = f"""
You are an expert Vedic astrology assistant helping users get the most out of a conversation with an astrologer.

Based on the astrologer's response below, generate exactly 3 short, clickable follow-up questions.

STRICT RULES:
- Question 1 MUST always be about gemstones OR remedies (Upayas) relevant to the planet or issue mentioned. Examples: "Which gemstone should I wear for this?", "What remedy can reduce Rahu's effect?", "Which stone strengthens Jupiter for wealth?", "Should I wear Blue Sapphire for Saturn?", "What is the best remedy for my marriage?".
- Question 2 should ask for more detail or timing about the prediction just given.
- Question 3 should explore a related astrological topic (different life area, dasha, or planetary transit).

Output EXACTLY a JSON array of 3 strings. Example: ["Gemstone/remedy question?", "Detail/timing question?", "Related topic question?"]

Do NOT output anything else. No markdown. No intro text. No explanations.

Language for questions: {language}

Astrologer Response:
{response_text}
"""

        try:

            raw_response = self.generate(
                prompt=prompt,
                json_format=True,
                temperature=0.3
            )

            cleaned = raw_response.strip()

            # Try parsing as JSON
            try:

                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]

                if cleaned.startswith("```"):
                    cleaned = cleaned[3:]

                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]

                cleaned = cleaned.strip()

                parsed = json.loads(cleaned)

                if isinstance(parsed, list):
                    return [
                        str(q)
                        for q in parsed[:3]
                    ]

                elif isinstance(parsed, dict):

                    for k, v in parsed.items():

                        if isinstance(v, list):
                            return [
                                str(q)
                                for q in v[:3]
                            ]

            except json.JSONDecodeError:
                pass

            # Regex fallback if JSON fails
            questions = re.findall(
                r'"([^"]+\?)"',
                raw_response
            )

            if questions:
                return questions[:3]

            return []

        except Exception as e:

            logger.error(
                f"Failed to generate followups: {e}"
            )

            return []


llm_service = LLMService()