"""
Professional 3-page Kundli PDF report generator.

Page 1 — Birth details + planetary positions table
Page 2 — Life-analysis sections (short, deterministic-first with LLM polish)
Page 3 — Dasha timeline + life periods + summary

Deliberately deterministic where it can be (chart facts, house lords) and
only uses the LLM for short narrative polish — with a plain-text fallback
if the LLM call fails, so a slow/unavailable Ollama never breaks the PDF.
"""
import json
from datetime import date
from io import BytesIO
from typing import Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
)

from app.memory.database import db
from app.services.kundli_service import get_house_lord
from app.services.topic_service import (
    TOPIC_CHART_FACTORS, get_house_for_sign, get_sign_for_house
)
from app.services.llm_service import llm_service
from app.utils.logger import logger

ACCENT = colors.HexColor("#b45309")   # amber-700
DARK = colors.HexColor("#1e293b")     # slate-800
MUTED = colors.HexColor("#64748b")    # slate-500
LIGHT_BG = colors.HexColor("#f8fafc") # slate-50

SECTION_PLAN = [
    # (title, topic key for TOPIC_CHART_FACTORS, extra houses to fold in)
    ("Personality & Life Path", None, [1]),
    ("Education & Intelligence", "education", [4]),
    ("Career & Finance", "career", [2, 11]),
    ("Marriage & Relationships", "marriage", []),
    ("Family & Social Life", None, [2, 4, 11]),
    ("Travel / Foreign Opportunities", None, [9, 12]),
]

LABELS = {
    "English": {
        "title": "JANAM KUNDLI",
        "subtitle": "Vedic Birth Chart Report",
        "birth_details": "Birth Details",
        "planetary_positions": "Planetary Positions",
        "name": "Name", "dob": "Date of Birth", "time": "Time", "place": "Place",
        "lagna": "Lagna (Ascendant)", "moon_sign": "Moon Sign", "nakshatra": "Nakshatra",
        "planet": "Planet", "sign": "Sign", "house": "House",
        "life_analysis": "Life Analysis",
        "explore": "Explore this house further inside the app for a detailed, interactive reading.",
        "dasha_timeline": "Current Dasha Period",
        "life_periods": "Major Life Periods",
        "summary": "Kundli Summary",
        "strengths": "Strengths", "challenges": "Challenges",
        "career_dir": "Career Direction", "relationships": "Relationships", "themes": "Overall Life Themes",
        "disclaimer": "This report provides a traditional Vedic astrology interpretation based on the "
                       "supplied birth details and chart. Astrological interpretations are not guaranteed predictions.",
        "period": "Period", "theme": "Main Theme", "current": "Current",
    },
    "Hindi": {
        "title": "जन्म कुंडली",
        "subtitle": "वैदिक जन्म कुंडली रिपोर्ट",
        "birth_details": "जन्म विवरण",
        "planetary_positions": "ग्रहों की स्थिति",
        "name": "नाम", "dob": "जन्म तिथि", "time": "समय", "place": "स्थान",
        "lagna": "लग्न", "moon_sign": "चंद्र राशि", "nakshatra": "नक्षत्र",
        "planet": "ग्रह", "sign": "राशि", "house": "भाव",
        "life_analysis": "जीवन विश्लेषण",
        "explore": "विस्तृत विवरण के लिए ऐप में इस भाव को एक्सप्लोर करें।",
        "dasha_timeline": "वर्तमान दशा अवधि",
        "life_periods": "प्रमुख जीवन काल",
        "summary": "कुंडली सारांश",
        "strengths": "शक्तियाँ", "challenges": "चुनौतियाँ",
        "career_dir": "करियर दिशा", "relationships": "रिश्ते", "themes": "समग्र जीवन विषय",
        "disclaimer": "यह रिपोर्ट दी गई जन्म तिथि और कुंडली के आधार पर पारंपरिक वैदिक ज्योतिष व्याख्या प्रस्तुत करती है। "
                       "ज्योतिषीय व्याख्याएँ सुनिश्चित भविष्यवाणियाँ नहीं हैं।",
        "period": "काल", "theme": "मुख्य विषय", "current": "वर्तमान",
    },
    "Hinglish": {
        "title": "JANAM KUNDLI",
        "subtitle": "Vedic Birth Chart Report",
        "birth_details": "Birth Details",
        "planetary_positions": "Planetary Positions",
        "name": "Name", "dob": "Date of Birth", "time": "Time", "place": "Place",
        "lagna": "Lagna", "moon_sign": "Moon Sign", "nakshatra": "Nakshatra",
        "planet": "Planet", "sign": "Sign", "house": "House",
        "life_analysis": "Life Analysis",
        "explore": "App mein iss house ko explore karein poora detailed reading ke liye.",
        "dasha_timeline": "Current Dasha Period",
        "life_periods": "Major Life Periods",
        "summary": "Kundli Summary",
        "strengths": "Strengths", "challenges": "Challenges",
        "career_dir": "Career Direction", "relationships": "Relationships", "themes": "Overall Life Themes",
        "disclaimer": "Yeh report diye gaye birth details aur chart ke aadhar par traditional Vedic astrology "
                       "interpretation deti hai. Astrological interpretations guaranteed predictions nahi hain.",
        "period": "Period", "theme": "Main Theme", "current": "Current",
    },
}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("ReportTitle", parent=ss["Title"], textColor=ACCENT, fontSize=22, spaceAfter=2))
    ss.add(ParagraphStyle("ReportSubtitle", parent=ss["Normal"], textColor=MUTED, fontSize=10, spaceAfter=14))
    ss.add(ParagraphStyle("SectionHeading", parent=ss["Heading2"], textColor=DARK, fontSize=13,
                           spaceBefore=14, spaceAfter=6, borderColor=ACCENT))
    ss.add(ParagraphStyle("SubHeading", parent=ss["Heading3"], textColor=ACCENT, fontSize=11, spaceBefore=10, spaceAfter=4))
    ss.add(ParagraphStyle("Body", parent=ss["Normal"], fontSize=9.5, leading=13.5, textColor=DARK))
    ss.add(ParagraphStyle("Explore", parent=ss["Normal"], fontSize=8, leading=11, textColor=MUTED, italic=True))
    ss.add(ParagraphStyle("Footer", parent=ss["Normal"], fontSize=7.5, leading=10, textColor=MUTED))
    return ss


def _get_verified_chart(session: Dict) -> Optional[Dict]:
    raw = session.get("kundli_raw")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    planets = parsed.get("planets") or []
    ascendant_sign = parsed.get("ascendant_sign")
    if not ascendant_sign or not planets:
        return None
    return {"ascendant_sign": ascendant_sign, "planets": planets}


def _get_dasha(session: Dict) -> Optional[Dict]:
    raw = session.get("kundli_dasha")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _get_nakshatra(session: Dict) -> str:
    """Best-effort extraction — the raw Kundli API payload carries this
    under planet_lords.Moon in most integrations. Falls back gracefully
    since the exact key can vary by provider."""
    raw = session.get("kundli_full_raw")
    if not raw:
        return "—"
    try:
        parsed = json.loads(raw)
        moon = parsed.get("planet_lords", {}).get("Moon", {})
        for key in ("nakshatra", "nakshatra_name", "star", "star_lord_nakshatra"):
            if moon.get(key):
                return str(moon[key])
    except Exception:
        pass
    return "—"


def _build_planet_table_rows(chart: Dict, L: Dict) -> List[List[str]]:
    ascendant_sign = chart["ascendant_sign"]
    rows = [[L["planet"], L["sign"], L["house"]]]
    for p in chart["planets"]:
        name = p.get("name", "")
        sign = p.get("sign_name", "")
        house = get_house_for_sign(sign, ascendant_sign)
        retro = " (R)" if str(p.get("isRetro", "")).lower() == "true" else ""
        rows.append([f"{name}{retro}", sign, str(house) if house else "—"])
    return rows


def _get_moon_sign(chart: Dict) -> str:
    for p in chart["planets"]:
        if p.get("name") == "Moon":
            return p.get("sign_name", "—")
    return "—"


SECTION_FALLBACK_TEXT = {
    "English": "Not enough chart data was available to generate a detailed reading for this area.",
    "Hindi": "इस क्षेत्र के लिए विस्तृत विवरण हेतु पर्याप्त कुंडली डेटा उपलब्ध नहीं है।",
    "Hinglish": "Iss area ke liye detailed reading banane ke liye kaafi chart data available nahi hai.",
}

SECTION_PROMPT = """You are an experienced Vedic Astrologer writing ONE short section of a printed Kundli
report titled "{section_title}".

Respond STRICTLY in {language} (Hindi: Devanagari; Hinglish: Latin-script conversational; English: warm English).
Length: 60-80 words, plain prose, no bullet points, no headers, no source references.
Speak with grounded confidence directly from the chart facts given — never mention books, RAG, or retrieval.

Relevant chart facts for this section:
{facts}

Write the section now:
"""


def _build_section_facts(topic: Optional[str], extra_houses: List[int], chart: Dict, dasha_info: Optional[Dict]) -> str:
    ascendant_sign = chart["ascendant_sign"]
    lines = [f"Ascendant: {ascendant_sign}"]

    houses_to_cover = set(extra_houses)
    planets_to_cover = set()
    if topic and topic in TOPIC_CHART_FACTORS:
        cfg = TOPIC_CHART_FACTORS[topic]
        houses_to_cover.add(cfg["house"])
        planets_to_cover.update(cfg["planets"])

    for h in sorted(houses_to_cover):
        lord = get_house_lord(h, ascendant_sign)
        sign = get_sign_for_house(h, ascendant_sign)
        occupants = [p["name"] for p in chart["planets"]
                     if get_house_for_sign(p.get("sign_name", ""), ascendant_sign) == h]
        occ_str = f", occupied by {', '.join(occupants)}" if occupants else ""
        lines.append(f"House {h}: sign {sign}, lord {lord or 'unknown'}{occ_str}")

    for planet_name in planets_to_cover:
        match = next((p for p in chart["planets"] if p.get("name") == planet_name), None)
        if match:
            sign = match.get("sign_name", "")
            house = get_house_for_sign(sign, ascendant_sign)
            lines.append(f"{planet_name}: {sign} (house {house})")

    if dasha_info:
        maha = dasha_info.get("current_mahadasha", {}) or {}
        antar = dasha_info.get("current_antardasha", {}) or {}
        if maha.get("lord"):
            timing = f"Current Dasha: {maha['lord']} Mahadasha"
            if antar.get("lord"):
                timing += f" - {antar['lord']} Antardasha"
            lines.append(timing)

    return "\n".join(lines)


def _generate_section_text(section_title: str, topic: Optional[str], extra_houses: List[int],
                            chart: Dict, dasha_info: Optional[Dict], language: str) -> str:
    facts = _build_section_facts(topic, extra_houses, chart, dasha_info)
    try:
        prompt = SECTION_PROMPT.format(section_title=section_title, language=language, facts=facts)
        text = llm_service.generate(prompt=prompt, temperature=0.5).strip()
        if text:
            return text
    except Exception as e:
        logger.warning(f"[KundliReport] section generation failed for '{section_title}': {e}")
    return SECTION_FALLBACK_TEXT.get(language, SECTION_FALLBACK_TEXT["Hinglish"])


SUMMARY_PROMPT = """You are a Vedic Astrologer closing out a printed Kundli report with a short summary.
Respond STRICTLY in {language}. Produce EXACTLY these five short items (1 sentence each, no more than
18 words per line, no bullets/markdown symbols — just the label and a colon):

Strengths: ...
Challenges: ...
Career Direction: ...
Relationships: ...
Overall Life Themes: ...

Base it only on these chart facts:
{facts}
"""


def _parse_summary(raw: str, L: Dict) -> Dict[str, str]:
    keys = {
        "Strengths": L["strengths"], "Challenges": L["challenges"],
        "Career Direction": L["career_dir"], "Relationships": L["relationships"],
        "Overall Life Themes": L["themes"],
    }
    result = {v: "" for v in keys.values()}
    for line in raw.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        label, _, value = line.partition(":")
        label = label.strip()
        for eng_key, local_label in keys.items():
            if label.lower().startswith(eng_key.lower()) or label == local_label:
                result[local_label] = value.strip()
    return result


def _generate_summary(chart: Dict, dasha_info: Optional[Dict], yoga_text: str, language: str, L: Dict) -> Dict[str, str]:
    ascendant_sign = chart["ascendant_sign"]
    facts_lines = [f"Ascendant: {ascendant_sign}"]
    for p in chart["planets"]:
        house = get_house_for_sign(p.get("sign_name", ""), ascendant_sign)
        facts_lines.append(f"{p['name']}: {p.get('sign_name')} (house {house})")
    if dasha_info:
        maha = dasha_info.get("current_mahadasha", {}) or {}
        if maha.get("lord"):
            facts_lines.append(f"Current Mahadasha: {maha['lord']}")
    if yoga_text:
        facts_lines.append(yoga_text)
    facts = "\n".join(facts_lines)

    fallback = {
        L["strengths"]: "—", L["challenges"]: "—", L["career_dir"]: "—",
        L["relationships"]: "—", L["themes"]: "—",
    }
    try:
        prompt = SUMMARY_PROMPT.format(language=language, facts=facts)
        raw = llm_service.generate(prompt=prompt, temperature=0.5).strip()
        parsed = _parse_summary(raw, L)
        if any(parsed.values()):
            for k, v in parsed.items():
                if not v:
                    parsed[k] = "—"
            return parsed
    except Exception as e:
        logger.warning(f"[KundliReport] summary generation failed: {e}")
    return fallback


def generate_kundli_report_pdf(session_id: str, language: str) -> bytes:
    session = db.get_or_create_session(session_id)
    chart = _get_verified_chart(session)
    if not chart:
        raise ValueError("No chart data available for this session.")

    L = LABELS.get(language, LABELS["Hinglish"])
    styles = _styles()
    dasha_info = _get_dasha(session)
    yoga_text = session.get("yoga_text") or ""

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.6 * cm, bottomMargin=1.6 * cm, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )
    story = []

    # ---------------- PAGE 1 ----------------
    story.append(Paragraph(L["title"], styles["ReportTitle"]))
    story.append(Paragraph(L["subtitle"], styles["ReportSubtitle"]))
    story.append(HRFlowable(width="100%", color=ACCENT, thickness=1.2, spaceAfter=12))

    story.append(Paragraph(L["birth_details"], styles["SectionHeading"]))
    birth_rows = [
        [L["name"], session.get("name") or "—"],
        [L["dob"], session.get("dob") or "—"],
        [L["time"], session.get("birth_time") or "—"],
        [L["place"], session.get("birth_place") or "—"],
        [L["lagna"], chart["ascendant_sign"]],
        [L["moon_sign"], _get_moon_sign(chart)],
        [L["nakshatra"], _get_nakshatra(session)],
    ]
    birth_table = Table(birth_rows, colWidths=[5 * cm, 10 * cm])
    birth_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), DARK),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e2e8f0")),
    ]))
    story.append(birth_table)
    story.append(Spacer(1, 16))

    story.append(Paragraph(L["planetary_positions"], styles["SectionHeading"]))
    planet_rows = _build_planet_table_rows(chart, L)
    planet_table = Table(planet_rows, colWidths=[5 * cm, 5 * cm, 5 * cm])
    planet_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
    ]))
    story.append(planet_table)
    story.append(PageBreak())

    # ---------------- PAGE 2 — LIFE ANALYSIS ----------------
    story.append(Paragraph(L["life_analysis"], styles["SectionHeading"]))
    for title, topic, extra_houses in SECTION_PLAN:
        text = _generate_section_text(title, topic, extra_houses, chart, dasha_info, language)
        story.append(Paragraph(title, styles["SubHeading"]))
        story.append(Paragraph(text, styles["Body"]))

        houses_mentioned = sorted(set(extra_houses) | ({TOPIC_CHART_FACTORS[topic]["house"]} if topic else set()))
        if houses_mentioned:
            house_list = ", ".join(f"House {h}" for h in houses_mentioned)
            story.append(Paragraph(f"→ {L['explore']} ({house_list})", styles["Explore"]))
        story.append(Spacer(1, 6))
    story.append(PageBreak())

    # ---------------- PAGE 3 — DASHA + SUMMARY ----------------
    story.append(Paragraph(L["dasha_timeline"], styles["SectionHeading"]))
    if dasha_info:
        maha = dasha_info.get("current_mahadasha", {}) or {}
        antar = dasha_info.get("current_antardasha", {}) or {}
        praty = dasha_info.get("current_pratyantardasha", {}) or {}

        dasha_rows = [[L["period"], L["theme"]]]
        if maha.get("lord"):
            start = (maha.get("start") or "").split(" ")[0]
            end = (maha.get("end") or "").split(" ")[0]
            span = f"{start} — {end}" if start and end else ""
            dasha_rows.append([f"{maha['lord']} Mahadasha\n{span}", L["current"]])
        if antar.get("lord"):
            dasha_rows.append([f"↳ {antar['lord']} Antardasha", "—"])
        if praty.get("lord"):
            dasha_rows.append([f"   ↳ {praty['lord']} Pratyantardasha", "—"])

        dasha_table = Table(dasha_rows, colWidths=[9 * cm, 6 * cm])
        dasha_table.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(dasha_table)
    else:
        story.append(Paragraph(
            "Dasha timing data is not available for this chart right now.",
            styles["Body"]
        ))
    story.append(Spacer(1, 14))

    story.append(Paragraph(L["summary"], styles["SectionHeading"]))
    summary = _generate_summary(chart, dasha_info, yoga_text, language, L)
    for label, value in summary.items():
        story.append(Paragraph(f"<b>{label}:</b> {value}", styles["Body"]))
        story.append(Spacer(1, 3))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0"), thickness=0.8, spaceAfter=6))
    story.append(Paragraph(L["disclaimer"], styles["Footer"]))
    story.append(Paragraph(f"Generated on {date.today().strftime('%d %B %Y')} — Call-Astro", styles["Footer"]))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes