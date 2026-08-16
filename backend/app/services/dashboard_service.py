from datetime import date
from typing import Optional
from app.services.llm_service import llm_service
from app.utils.logger import logger
from datetime import date, timedelta

MOON_SIGN_COLORS = {
    "Aries": "Red", "Taurus": "Green", "Gemini": "Yellow",
    "Cancer": "White", "Leo": "Gold", "Virgo": "Emerald Green",
    "Libra": "Sky Blue", "Scorpio": "Maroon", "Sagittarius": "Purple",
    "Capricorn": "Navy Blue", "Aquarius": "Turquoise", "Pisces": "Sea Green",
}

DAILY_PREDICTION_PROMPT = """You are a warm, experienced Indian Vedic Astrologer writing a short daily
reflection for a client, based on their birth chart.

Rules:
1. Respond in {language}.
2. Length: 2-3 short sentences, max 50 words. WhatsApp-style, warm and encouraging.
3. Frame this as general daily guidance rooted in their natal chart, NOT a precise transit calculation.
4. Do NOT mention specific times, hours, or numeric scores.
5. Do NOT reference any technical process.

Birth Chart Summary:
{kundli_summary}

Today's Date: {today}

Write today's short reflection:
"""

def get_lucky_color(moon_sign: Optional[str]) -> str:
    if not moon_sign:
        return "Not available"
    return MOON_SIGN_COLORS.get(moon_sign, "Not available")

def generate_daily_prediction(kundli_summary: str, language: str) -> Optional[str]:
    """Returns the generated prediction, or None if generation failed —
    callers should NOT cache a None result, so a transient Ollama failure
    doesn't lock in a generic fallback for the rest of the day."""
    try:
        prompt = DAILY_PREDICTION_PROMPT.format(
            language=language,
            kundli_summary=kundli_summary or "No chart data available.",
            today=date.today().strftime("%d %B %Y"),
        )
        result = llm_service.generate(prompt=prompt, temperature=0.7).strip()
        if not result:
            logger.warning("Daily prediction generation returned empty response")
            return None
        return result
    except Exception as e:
        logger.error(f"Daily prediction generation failed: {e}")
        return None


WEEKLY_GUIDANCE_PROMPT = """You are a warm, experienced Indian Vedic Astrologer writing a short weekly
reflection for your client {name}, based on their birth chart and current planetary period (Dasha).

Rules:
1. Respond in {language}.
2. Length: 3-4 short sentences, max 70 words. WhatsApp-style, warm and encouraging.
3. Ground this in their natal chart and current Mahadasha/Antardasha period — this is
   real astrological data, not a guess. Do NOT mention specific transit positions,
   since current planetary transit data is not available to you.
4. Frame this as general weekly guidance for reflection, not a precise prediction.
5. Do NOT mention specific numeric scores or exact dates/times.
6. Do NOT reference any technical process.
7. Address the client by their name {name} naturally.

Birth Chart Summary:
{kundli_summary}

Current Dasha Period:
{dasha_summary}

This Week's Date Range: {week_start} to {week_end}

Write this week's short reflection:
"""

def generate_weekly_guidance(kundli_summary: str, dasha_summary: str, language: str, name: str) -> Optional[str]:
    """Weekly reflection grounded in natal chart + current REAL dasha period.
    Returns None on failure — caller should not cache a failed generation."""
    try:
        today = date.today()
        week_start = today.strftime("%d %b")
        week_end = (today + timedelta(days=6)).strftime("%d %b")

        prompt = WEEKLY_GUIDANCE_PROMPT.format(
            name=name or "Client",
            language=language,
            kundli_summary=kundli_summary or "No chart data available.",
            dasha_summary=dasha_summary or "No dasha data available.",
            week_start=week_start,
            week_end=week_end,
        )
        result = llm_service.generate(prompt=prompt, temperature=0.7).strip()
        if not result:
            logger.warning("Weekly guidance generation returned empty response")
            return None
        return result
    except Exception as e:
        logger.error(f"Weekly guidance generation failed: {e}")
        return None