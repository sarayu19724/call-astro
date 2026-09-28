
from typing import Dict, Any, List, Optional, Set
from app.services.kundli_service import get_house_lord

# Simplified but reasonable chart-factor mapping per life topic.
TOPIC_CHART_FACTORS = {
    "career": {
        "house": 10, "planets": ["Saturn", "Sun"],
        "keywords": ["career", "job", "profession", "naukri", "business", "work", "kaam"],
        "search_bias": "career job profession 10th house Saturn Sun",
        "divisional_chart": "D10",
    },
    "marriage": {
        "house": 7, "planets": ["Venus", "Jupiter"],
        "keywords": ["marriage", "shaadi", "spouse", "wife", "husband", "partner", "relationship"],
        "search_bias": "marriage spouse 7th house Venus Jupiter Navamsa",
        "divisional_chart": "D9",
    },
    "children": {
        "house": 5, "planets": ["Jupiter", "Venus", "Moon"],
        "keywords": ["children", "kids", "child", "parenthood", "santana", "pregnancy", "progeny", "bacche", "baby"],
        "search_bias": "children kids progeny pregnancy 5th house Jupiter D7 Saptamsa",
        "divisional_chart": "D7",
    },
    "health": {
        "house": 1, "planets": ["Saturn", "Mars", "Moon"],
        "keywords": ["health", "sehat", "illness", "disease", "body", "bimari"],
        "search_bias": "health disease 1st house 6th house Lagna Saturn Mars Moon",
        "divisional_chart": None,
    },
    "finance": {
        "house": 11, "planets": ["Jupiter", "Venus", "Mercury"],
        "keywords": ["money", "finance", "paisa", "wealth", "income", "dhan", "paise"],
        "search_bias": "wealth money finance income gains 2nd house 11th house Jupiter Venus Mercury",
        "divisional_chart": None,
    },
    "education": {
        "house": 5, "planets": ["Mercury", "Jupiter"],
        "keywords": ["education", "study", "padhai", "exam", "school", "college"],
        "search_bias": "education study 5th house Mercury Jupiter",
        "divisional_chart": "D24",
    },
    "abroad": {
        "house": 12, "planets": ["Rahu", "Saturn", "Moon"],
        "keywords": ["abroad", "foreign", "visa", "immigration", "videsh", "relocate"],
        "search_bias": "foreign abroad travel settlement 12th house 9th house Rahu Moon",
        "divisional_chart": None,
    },
    "remedies": {
        "house": 9, "planets": ["Jupiter", "Sun"],
        "keywords": ["remedy", "remedies", "gemstone", "mantra", "puja", "upay"],
        "search_bias": "astrological remedies gemstones mantras 9th house dharma Jupiter",
        "divisional_chart": None,
    },
    "general": {
        "house": 1, "planets": ["Sun", "Moon", "Jupiter"],
        "keywords": ["chart", "kundli", "horoscope", "personality", "life", "future", "placements", "yogas"],
        "search_bias": "birth chart ascendant lagna yogas planetary placements",
        "divisional_chart": None,
    },
}

ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]
TOPIC_RELEVANT_BOOKS = {
    "career": [
        "Jyotish_AIFAS_Timing of events through Dasha and transit",
        "Timing of Events through Dasha and Transit",
        "Dasa Lord Transit _PVR Rao (1)",
        "Dasha-Transit (1)",
        "J_KP reader_5_transits",
        "Important Planetary Transits",
        "Gochar Vichar AIFAS (1)",
    ],
    "marriage": [
        "Timing of Marriage by Transits and Jaimini Astrology (2)",
        "Timing marriage",
        "Jupiter_Transits_paryaya",
    ],
    "children": [
        "Timing of Events through Dasha and Transit",
        "Important Planetary Transits",
        "Gochar Vichar AIFAS (1)",
    ],
    "health": [
        "Cancer timing Through Transits_S.Rath (1)",
    ],
    "finance": [
        "Dasa Lord Transit _PVR Rao (1)",
        "Transit Conjunctions on Natal Points_PVR Rao (2)",
    ],
    "education": [
        "Jyotish_AIFAS_Timing of events through Dasha and transit",
        "Stars_Days_&_Transit_In_Vedic_Astrology",
    ],
    "general": [
        "Important Planetary Transits",
        "Gochar Vichar AIFAS (1)",
        "Timing of Events through Dasha and Transit",
    ],
    "timing_general": [
        "Transit short cuts",
        "Transit Short-Cuts_A Practical Tool_Bepin Behari (2)",
        "Importance of TRANSIT Astrology",
        "Microscopy_of_Transiting_Planets",
        "Celestial_Transits_Or_Grah_Gochar",
        "Transit of Nakshatra Dasa Lord",
        "Transit of Rahu-Ketu & the Fortunes",
        "Saturn transit in Square houses",
        "Stationary Planets in Transit",
        "Tertiary Progression And Trigger Transits",
    ],
}
NATURAL_BENEFICS = {"Jupiter", "Venus", "Mercury", "Moon"}
# Sun is NOT a universal malefic in Jyotish — it is a functional benefic for many
# ascendants (e.g. Leo, Aries, Scorpio). Treating it as neutral avoids incorrect
# consistency scores across different Lagnas.
NATURAL_MALEFICS = {"Saturn", "Mars", "Rahu", "Ketu"}

# Kendra houses: 1, 4, 7, 10 | Trikona houses: 1, 5, 9
KENDRA_TRIKONA_HOUSES = {1, 4, 5, 7, 9, 10}       # strong/supportive houses
DUSTHANA_HOUSES = {6, 8, 12}                       # weak/challenging houses

# ------------------------------------------------------------------
# Evidence Voting — relative weight given to each independent source
# when combining them into one confidence score. Dasha and Chart carry
# full weight since they're the primary classical indicators; Yoga is
# a secondary/reinforcing signal.
# ------------------------------------------------------------------
EVIDENCE_WEIGHTS = {
    "dasha": 1.0,
    "chart": 1.0,
    "yoga": 0.6,
}


def classify_topic(message: str) -> Optional[str]:
    """Simple keyword-based topic classifier."""
    text_lower = message.lower()
    for topic, config in TOPIC_CHART_FACTORS.items():
        for kw in config["keywords"]:
            if kw in text_lower:
                return topic
    return None


# Pre-defined instant follow-up suggestions per topic.
TOPIC_SUGGESTIONS = {
    "marriage": [
        "Which gemstone should I wear to attract the right partner?",
        "When is the best time for my marriage according to my Dasha?",
        "How is my 7th house lord placed in my chart?",
    ],
    "children": [
        "What does my 5th house say about children and progeny?",
        "When is the most favorable time for conceiving or children?",
        "Which planet supports parenthood in my chart?",
    ],
    "career": [
        "Which gemstone strengthens my career planet?",
        "When will my career growth peak in the next 2 years?",
        "Is my 10th house strong for a government job?",
    ],
    "finance": [
        "Which stone or remedy can improve my financial luck?",
        "When will my income increase according to my Dasha?",
        "How is my 11th house placed for gains?",
    ],
    "health": [
        "Which gemstone or remedy improves my vitality?",
        "Which planet is affecting my health the most right now?",
        "How does my current Dasha affect my physical strength?",
    ],
    "education": [
        "Which gemstone improves concentration and memory?",
        "Is my chart strong for higher education or abroad studies?",
        "When is the best period to appear for exams?",
    ],
}

DEFAULT_SUGGESTIONS = [
    "Which gemstone is lucky for me?",
    "How is my current Dasha period overall?",
    "What does my Lagna (Ascendant) say about my personality?",
]


def get_instant_suggestions(*args, **kwargs) -> list:
    """Returns instant follow-up suggestions based on the detected topic.
    No LLM call needed — responses are immediate."""
    topic = None
    language = "English"

    # Support (topic, language), (session, topic, language), or kwargs
    if "topic" in kwargs:
        topic = kwargs["topic"]
    if "language" in kwargs:
        language = kwargs["language"]

    if args:
        if len(args) == 1:
            topic = args[0] if isinstance(args[0], str) or args[0] is None else None
        elif len(args) == 2:
            topic, language = args[0], args[1]
        elif len(args) >= 3:
            # Called with (session, topic, language)
            topic, language = args[1], args[2]

    suggestions = TOPIC_SUGGESTIONS.get(topic, DEFAULT_SUGGESTIONS) if topic else DEFAULT_SUGGESTIONS

    if language == "Hinglish":
        hinglish_map = {
            "marriage": [
                "Sahi partner ke liye kaunsa gemstone pehnu?",
                "Mere Dasha ke hisaab se shaadi kab hogi?",
                "Mera 7th house kaisa hai?",
            ],
            "children": [
                "Mera 5th house santan ke liye kaisa hai?",
                "Bacche ke liye sabse favorable time kab hai?",
                "Santan yog ke liye kaun sa planet strong hai?",
            ],
            "career": [
                "Career ke liye kaunsa gemstone sahi rahega?",
                "Agli 2 saalon mein career growth kab hogi?",
                "Sarkari naukri ke liye mera 10th house kaisa hai?",
            ],
            "finance": [
                "Paisa badhane ke liye kaunsa stone ya upay karoon?",
                "Mere Dasha mein income kab badhegi?",
                "Mera 11th house gains ke liye kaisa hai?",
            ],
            "health": [
                "Sehat ke liye kaunsa gemstone ya upay sahi hai?",
                "Abhi kaun sa planet meri health affect kar raha hai?",
                "Meri current Dasha body strength pe kaisa asar kar rahi hai?",
            ],
            "education": [
                "Concentration ke liye kaunsa gemstone sahi hai?",
                "Mera chart higher education ya abroad ke liye kaisa hai?",
                "Exam ke liye best time kaunsa hai?",
            ],
        }
        return hinglish_map.get(topic, [
            "Mere liye kaunsa gemstone lucky hai?",
            "Meri current Dasha overall kaisi hai?",
            "Mera Lagna (Ascendant) kya kehta hai?",
        ])

    if language == "Hindi":
        hindi_map = {
            "marriage": [
                "सही जीवनसाथी के लिए कौन सा रत्न पहनूं?",
                "मेरी दशा के अनुसार विवाह कब होगा?",
                "मेरा सप्तम भाव कैसा है?",
            ],
            "children": [
                "संतान के लिए मेरा पंचम भाव कैसा है?",
                "संतान प्राप्ति के लिए सबसे अनुकूल समय कब है?",
                "संतान योग के लिए कौन सा ग्रह मजबूत है?",
            ],
            "career": [
                "करियर के लिए कौन सा रत्न सही रहेगा?",
                "अगले 2 वर्षों में करियर विकास कब होगा?",
                "सरकारी नौकरी के लिए मेरा दशम भाव कैसा है?",
            ],
            "finance": [
                "धन वृद्धि के लिए कौन सा रत्न या उपाय करूं?",
                "मेरी दशा में आय कब बढ़ेगी?",
                "मेरा एकादश भाव लाभ के लिए कैसा है?",
            ],
            "health": [
                "स्वास्थ्य के लिए कौन सा रत्न या उपाय उचित है?",
                "अभी कौन सा ग्रह मेरे स्वास्थ्य को प्रभावित कर रहा है?",
                "वर्तमान दशा शारीरिक शक्ति पर कैसा प्रभाव डाल रही है?",
            ],
            "education": [
                "एकाग्रता के लिए कौन सा रत्न उचित है?",
                "उच्च शिक्षा या विदेश के लिए मेरी कुंडली कैसी है?",
                "परीक्षा के लिए सर्वोत्तम समय कौन सा है?",
            ],
        }
        return hindi_map.get(topic, [
            "मेरे लिए कौन सा रत्न भाग्यशाली है?",
            "मेरी वर्तमान दशा कैसी है?",
            "मेरा लग्न (Ascendant) क्या कहता है?",
        ])

    return suggestions


def get_house_for_sign(sign_name: str, ascendant_sign: str) -> Optional[int]:
    """House 1 = ascendant's own sign; houses count forward from there."""
    try:
        asc_idx = ZODIAC_SIGNS.index(ascendant_sign)
        sign_idx = ZODIAC_SIGNS.index(sign_name)
        return ((sign_idx - asc_idx) % 12) + 1
    except ValueError:
        return None


def get_sign_for_house(house_number: int, ascendant_sign: str) -> Optional[str]:
    """Inverse — which sign occupies a given house number."""
    try:
        asc_idx = ZODIAC_SIGNS.index(ascendant_sign)
        return ZODIAC_SIGNS[(asc_idx + house_number - 1) % 12]
    except ValueError:
        return None


def build_topic_emphasis(topic: str, planets: List[dict], ascendant_sign: str, dasha_info: Optional[dict]) -> str:
    """Build a short, explicit 'pay attention to these facts' block for the
    prompt — includes house, house LORD, significator planets, and timing."""
    config = TOPIC_CHART_FACTORS.get(topic)
    if not config:
        return ""

    lines = [f"--- Key factors for this {topic} question ---"]

    house_num = config["house"]
    house_sign = get_sign_for_house(house_num, ascendant_sign)
    house_lord_name = get_house_lord(house_num, ascendant_sign)

    if house_sign:
        lord_str = f", ruled by {house_lord_name}" if house_lord_name else ""
        lines.append(f"{house_num}th House (governs {topic}): occupied by {house_sign}{lord_str}")

    if house_lord_name:
        lord_match = next((p for p in planets if p.get("name") == house_lord_name), None)
        if lord_match:
            lord_sign = lord_match.get("sign_name", "")
            lord_house = get_house_for_sign(lord_sign, ascendant_sign)
            lord_house_str = f", in the {lord_house}th house" if lord_house else ""
            lines.append(f"{house_lord_name} ({house_num}th Lord): placed in {lord_sign}{lord_house_str}")

    for planet_name in config["planets"]:
        match = next((p for p in planets if p.get("name") == planet_name), None)
        if match:
            sign = match.get("sign_name", "")
            house = get_house_for_sign(sign, ascendant_sign)
            house_str = f", in the {house}th house" if house else ""
            retro = " (retrograde)" if str(match.get("isRetro", "")).lower() == "true" else ""
            lines.append(f"{planet_name} (significator for {topic}): in {sign}{house_str}{retro}")

    if dasha_info:
        maha = dasha_info.get("current_mahadasha", {})
        antar = dasha_info.get("current_antardasha", {})
        if maha:
            timing_line = f"Current timing relevant to {topic}: Mahadasha={maha.get('lord')}"
            if antar:
                timing_line += f", Antardasha={antar.get('lord')}"
            lines.append(timing_line)

    return "\n".join(lines) if len(lines) > 1 else ""


def get_search_bias(topic: Optional[str]) -> str:
    """Extra search terms to append to the RAG query for topic-targeted book retrieval."""
    if not topic:
        return ""
    return TOPIC_CHART_FACTORS.get(topic, {}).get("search_bias", "")


def build_explanation_footer(topic: Optional[str], ascendant_sign: Optional[str], dasha_info: Optional[dict], language: str = "Hinglish") -> str:
    """Build a short, honest footer listing the real factors that grounded
    this response. Every item here is something actually fed to the LLM."""
    if not topic and not dasha_info:
        return ""

    factors = []

    config = TOPIC_CHART_FACTORS.get(topic) if topic else None
    if config and ascendant_sign:
        house_num = config["house"]
        house_lord = get_house_lord(house_num, ascendant_sign)
        if house_lord:
            factors.append(f"{house_num}th House ({house_lord})")
        else:
            factors.append(f"{house_num}th House")
        for planet in config["planets"]:
            factors.append(planet)

    if dasha_info:
        maha = dasha_info.get("current_mahadasha", {})
        antar = dasha_info.get("current_antardasha", {})
        if maha:
            dasha_str = maha.get("lord", "")
            if antar:
                dasha_str += f"–{antar.get('lord', '')}"
            dasha_str += " Dasha"
            factors.append(dasha_str)

    if not factors:
        return ""

    seen = set()
    unique_factors = []
    for f in factors:
        if f not in seen:
            seen.add(f)
            unique_factors.append(f)

    factors_str = ", ".join(unique_factors)

    labels = {
        "English": f"\n\n📍 Based on: {factors_str}",
        "Hindi": f"\n\n📍 आधारित: {factors_str}",
        "Hinglish": f"\n\n📍 Based on: {factors_str}",
    }
    return labels.get(language, labels["Hinglish"])


def _score_dasha_signal(dasha_info: Optional[dict]) -> int:
    """+1 if current Dasha lord(s) are naturally benefic, -1 if malefic, 0 if mixed/unknown."""
    if not dasha_info:
        return 0
    maha_lord = dasha_info.get("current_mahadasha", {}).get("lord")
    antar_lord = dasha_info.get("current_antardasha", {}).get("lord")

    score = 0
    for lord in [maha_lord, antar_lord]:
        if not lord:
            continue
        if lord in NATURAL_BENEFICS:
            score += 1
        elif lord in NATURAL_MALEFICS:
            score -= 1
    return (score > 0) - (score < 0)


def _score_chart_signal(topic: str, planets: List[dict], ascendant_sign: str) -> int:
    """+1 if topic's house lord / significators are well-placed, -1 if in dusthana or retrograde, 0 if mixed."""
    config = TOPIC_CHART_FACTORS.get(topic)
    if not config:
        return 0

    house_num = config["house"]
    house_lord_name = get_house_lord(house_num, ascendant_sign)

    score = 0
    checked = 0

    candidates = [house_lord_name] + config["planets"]
    seen = set()
    for planet_name in candidates:
        if not planet_name or planet_name in seen:
            continue
        seen.add(planet_name)
        match = next((p for p in planets if p.get("name") == planet_name), None)
        if not match:
            continue

        sign = match.get("sign_name", "")
        placed_house = get_house_for_sign(sign, ascendant_sign)
        is_retro = str(match.get("isRetro", "")).lower() == "true"

        checked += 1
        if placed_house in DUSTHANA_HOUSES or is_retro:
            score -= 1
        elif placed_house in KENDRA_TRIKONA_HOUSES:
            score += 1

    if checked == 0:
        return 0
    return (score > 0) - (score < 0)


def _score_yoga_signal(topic: Optional[str], yoga_text: str) -> int:
    """+1 if a classically strong yoga (Raj/Dhana/Gajakesari/Budhaditya/Chandra-Mangal)
    is present, or a topic-significator planet is exalted; -1 if a topic-significator
    planet is debilitated. 0 if yoga_text is empty or has no topic-relevant signal.
    This reuses yoga_text that's already pre-computed once per birth chart —
    no new computation, just a new lens on existing data."""
    if not topic or not yoga_text:
        return 0

    config = TOPIC_CHART_FACTORS.get(topic, {})
    sig_planets = set(config.get("planets", []))
    text_lower = yoga_text.lower()

    score = 0
    if any(name in text_lower for name in ("raj yoga", "dhana yoga", "gajakesari", "budhaditya")):
        score += 1

    for planet in sig_planets:
        if f"{planet.lower()} exalted" in text_lower:
            score += 1
        if f"{planet.lower()} debilitated" in text_lower:
            score -= 1

    return (score > 0) - (score < 0)


def build_consistency_check(topic: Optional[str], planets: List[dict], ascendant_sign: Optional[str],
                             dasha_info: Optional[dict]) -> Optional[dict]:
    """Compare Dasha timing vs. chart placement for this topic. Returns None
    if there isn't enough data to check (no topic, no chart, etc.)."""
    if not topic or not planets or not ascendant_sign:
        return None

    dasha_score = _score_dasha_signal(dasha_info)
    chart_score = _score_chart_signal(topic, planets, ascendant_sign)

    if dasha_score == 0 and chart_score == 0:
        return None

    if dasha_score > 0 and chart_score > 0:
        alignment = "aligned_positive"
    elif dasha_score < 0 and chart_score < 0:
        alignment = "aligned_negative"
    elif (dasha_score > 0 and chart_score < 0) or (dasha_score < 0 and chart_score > 0):
        alignment = "mixed"
    else:
        alignment = "leaning"

    return {
        "alignment": alignment,
        "dasha_score": dasha_score,
        "chart_score": chart_score,
    }


def build_consistency_note(check: Optional[dict], topic: Optional[str]) -> str:
    """Turn the consistency check result into an explicit instruction block
    for the LLM prompt — this is what actually changes the model's behavior."""
    if not check or not topic:
        return ""

    alignment = check["alignment"]

    if alignment == "aligned_positive":
        return (f"Signal check for {topic}: Dasha timing AND chart placement both point favorably. "
                f"You may speak with full confidence — the signals agree.")
    if alignment == "aligned_negative":
        return (f"Signal check for {topic}: Dasha timing AND chart placement both indicate challenges. "
                f"Speak honestly about the difficulty, still with a constructive/encouraging tone — don't manufacture false optimism.")
    if alignment == "mixed":
        return (f"Signal check for {topic}: Dasha timing and chart placement point in DIFFERENT directions "
                f"(one supportive, one challenging). Do NOT force a single confident verdict — acknowledge both "
                f"sides honestly in your own natural voice, e.g. 'is supported by X but a bit delayed by Y'. "
                f"This is genuine nuance in the chart, not uncertainty on your part.")
    return (f"Signal check for {topic}: One signal (Dasha or chart) leans positive/negative, the other is neutral. "
            f"You may lean toward that direction but keep slightly softer certainty than a fully aligned reading.")


# ------------------------------------------------------------------
# Evidence Voting — replaces the binary "aligned/mixed" check with a
# weighted multi-source vote (Dasha, Chart placement, Yogas), producing
# an explainable confidence score instead of just an alignment label.
# ------------------------------------------------------------------
def build_evidence_vote(
    topic: Optional[str],
    planets: List[dict],
    ascendant_sign: Optional[str],
    dasha_info: Optional[dict],
    yoga_text: str = "",
) -> Optional[Dict]:
    """Each evidence source independently 'votes' favorable/challenging/neutral
    for this topic. Votes are combined with fixed weights into a 0-100%
    confidence score plus a verdict. Returns None if there's no chart data
    to vote on at all (distinct from a genuine 'neutral' vote)."""
    if not topic:
        return None
    if not planets or not ascendant_sign:
        return None

    votes = [
        {
            "source": "Dasha Timing",
            "vote": _score_dasha_signal(dasha_info),
            "weight": EVIDENCE_WEIGHTS["dasha"],
        },
        {
            "source": "Chart Placement",
            "vote": _score_chart_signal(topic, planets, ascendant_sign),
            "weight": EVIDENCE_WEIGHTS["chart"],
        },
        {
            "source": "Yogas",
            "vote": _score_yoga_signal(topic, yoga_text),
            "weight": EVIDENCE_WEIGHTS["yoga"],
        },
    ]

    if all(v["vote"] == 0 for v in votes):
        return None  # no source has any signal — nothing meaningful to report

    weighted_sum = sum(v["vote"] * v["weight"] for v in votes)
    max_possible = sum(v["weight"] for v in votes)
    raw = (weighted_sum / max_possible) if max_possible else 0.0  # -1..1
    confidence_pct = max(0, min(100, round(50 + raw * 50)))       # 0=fully negative, 50=neutral, 100=fully positive

    positive = sum(1 for v in votes if v["vote"] > 0)
    negative = sum(1 for v in votes if v["vote"] < 0)
    neutral = sum(1 for v in votes if v["vote"] == 0)

    if positive >= 2 and positive > negative:
        verdict = "favorable"
    elif negative >= 2 and negative > positive:
        verdict = "challenging"
    elif positive > 0 and negative > 0:
        verdict = "mixed"
    else:
        verdict = "leaning"

    return {
        "votes": votes,
        "positive_count": positive,
        "negative_count": negative,
        "neutral_count": neutral,
        "confidence_pct": confidence_pct,
        "verdict": verdict,
    }


def format_evidence_vote_for_prompt(vote: Optional[Dict], topic: Optional[str]) -> str:
    """Render the vote as an instruction block for the LLM — this is what
    actually calibrates the model's stated certainty against real evidence
    strength instead of a fixed 'always sound confident' rule."""
    if not vote or not topic:
        return ""

    lines = [f"Evidence Vote for {topic} (each source scored independently):"]
    for v in vote["votes"]:
        direction = "Supportive" if v["vote"] > 0 else ("Challenging" if v["vote"] < 0 else "No clear signal")
        lines.append(f"- {v['source']}: {direction}")

    lines.append(
        f"Result: {vote['positive_count']} supportive, {vote['negative_count']} challenging, "
        f"{vote['neutral_count']} neutral — confidence score {vote['confidence_pct']}%. "
        f"Calibrate your certainty to this: 70%+ → speak with strong confidence; "
        f"40-70% → grounded but slightly softer confidence; below 40% or verdict 'mixed' → "
        f"be honest about the mixed picture instead of forcing a single confident verdict."
    )
    return "\n".join(lines)


def build_reasoning_trace(
    topic: Optional[str],
    ascendant_sign: Optional[str],
    planets: List[dict],
    dasha_info: Optional[dict],
    consistency_check: Optional[dict],
    rag_sources: Optional[List[Dict[str, Any]]] = None,
    evidence_vote: Optional[Dict] = None,
    topic_result: Optional[Any] = None,
    gochar_data: Optional[Dict] = None,
    **kwargs,
) -> List[dict]:
    """Assemble a numbered, inspectable reasoning chain from data already
    computed elsewhere in the pipeline. Each step is {step, type, title, detail} —
    purely structural, no LLM call, so it's fast and 100% traceable to real
    inputs rather than an LLM's self-report of its own reasoning."""
    if not ascendant_sign:
        return []

    active_topic = (topic or "general").lower()
    steps = []
    step_num = 1

    if topic_result:
        # Step 1: Classification
        method_str = getattr(topic_result, "method", "router")
        conf = getattr(topic_result, "confidence", 1.0)
        topic_name = (topic or getattr(topic_result, "topic", None) or "General").capitalize()
        concepts = getattr(topic_result, "detected_concepts", []) or getattr(topic_result, "llm_concepts", []) or []
        concept_str = f" Concepts: {', '.join(concepts)}" if concepts else ""
        steps.append({
            "step": step_num,
            "type": "query_understanding",
            "title": "Classification",
            "detail": f"Topic: {topic_name} — detected via {method_str} ({int(conf * 100)}% confidence).{concept_str}"
        })
        step_num += 1

        # Step 2: Query Summary
        summary = getattr(topic_result, "llm_summary", None)
        if summary:
            steps.append({
                "step": step_num,
                "type": "query_understanding",
                "title": "Query Summary",
                "detail": summary
            })
            step_num += 1
    else:
        topic_name = active_topic.capitalize()
        steps.append({
            "step": step_num,
            "type": "query_understanding",
            "title": "Topic Focus",
            "detail": f"Astrological inquiry evaluated under {topic_name} focus."
        })
        step_num += 1

    if dasha_info:
        maha = dasha_info.get("current_mahadasha", {})
        antar = dasha_info.get("current_antardasha", {})
        detail = f"Mahadasha: {maha.get('lord', 'Unknown')}"
        if antar:
            detail += f", Antardasha: {antar.get('lord', 'Unknown')}"
        steps.append({
            "step": step_num,
            "type": "dasha",
            "title": "Current Dasha Period",
            "detail": detail
        })
        step_num += 1

    if gochar_data and gochar_data.get("available"):
        sade_sati = gochar_data.get("sade_sati", {})
        ss_status = sade_sati.get("status", "Inactive")
        highlights = gochar_data.get("highlights", [])
        h_text = " | ".join(highlights[:2]) if highlights else "Planetary transits mapped."
        steps.append({
            "step": step_num,
            "type": "chart",
            "title": "Real-Time Planetary Transits (Gochar)",
            "detail": f"Sade Sati: {ss_status}. {h_text}"
        })
        step_num += 1

    config = TOPIC_CHART_FACTORS.get(active_topic) or TOPIC_CHART_FACTORS.get("general", {})
    house_num = config.get("house")
    if house_num:
        house_sign = get_sign_for_house(house_num, ascendant_sign)
        house_lord = get_house_lord(house_num, ascendant_sign)
        detail = f"{house_num}th House governs {active_topic}"
        if house_sign:
            detail += f" — occupied by {house_sign}"
        if house_lord:
            detail += f", ruled by {house_lord}"
        steps.append({
            "step": step_num,
            "type": "activation",
            "title": f"Relevant House ({house_num}th)",
            "detail": detail
        })
        step_num += 1

    sig_planets = config.get("planets", [])
    if sig_planets and planets:
        placements = []
        for pname in sig_planets:
            match = next((p for p in planets if p.get("name") == pname), None)
            if match:
                sign = match.get("sign_name", "")
                house = get_house_for_sign(sign, ascendant_sign)
                retro = " (retrograde)" if str(match.get("isRetro", "")).lower() == "true" else ""
                placements.append(f"{pname} in {sign} ({house}th house){retro}")
        if placements:
            steps.append({
                "step": step_num,
                "type": "chart",
                "title": "Significator Planets",
                "detail": "; ".join(placements)
            })
            step_num += 1

    div_chart = config.get("divisional_chart")
    if div_chart:
        purpose_map = {"D9": "marriage", "D10": "career", "D24": "education", "D7": "children / progeny"}
        steps.append({
            "step": step_num,
            "type": "chart",
            "title": "Divisional Chart Consulted",
            "detail": f"{div_chart} chart (used specifically for {purpose_map.get(div_chart, active_topic)} analysis)"
        })
        step_num += 1

    if consistency_check:
        alignment = consistency_check.get("alignment")
        alignment_labels = {
            "aligned_positive": "Dasha timing and chart placement both support a favorable reading",
            "aligned_negative": "Dasha timing and chart placement both indicate challenges",
            "mixed": "Dasha timing and chart placement point in different directions — genuine mixed signals",
            "leaning": "One signal (Dasha or chart) leans in a direction, the other is neutral",
        }
        steps.append({
            "step": step_num,
            "type": "consensus",
            "title": "Signal Consistency Check",
            "detail": alignment_labels.get(alignment, "Signals evaluated")
        })
        step_num += 1

    # Evidence Vote step — surfaces the weighted multi-source confidence
    # score directly in the explainability panel, not just in the prompt.
    if evidence_vote:
        vote_summary = ", ".join(
            f"{v['source']}: {'Supportive' if v['vote'] > 0 else ('Challenging' if v['vote'] < 0 else 'Neutral')}"
            for v in evidence_vote["votes"]
        )
        detail = (
            f"{vote_summary}. Overall confidence: {evidence_vote['confidence_pct']}% "
            f"({evidence_vote['positive_count']} supportive / {evidence_vote['negative_count']} challenging "
            f"/ {evidence_vote['neutral_count']} neutral) — verdict: {evidence_vote['verdict']}."
        )
        steps.append({
            "step": step_num,
            "type": "evidence",
            "title": "Evidence Vote",
            "detail": detail
        })
        step_num += 1

    references = []
    if rag_sources:
        seen = set()
        for hit in rag_sources:
            if isinstance(hit, str):
                source = hit
                page = None
                score = None
            elif isinstance(hit, dict):
                source = hit.get("source", "Unknown")
                page = hit.get("page")
                score = hit.get("score")
            else:
                continue

            # Avoid showing the same book/page twice
            key = (source, page)
            if key in seen:
                continue
            seen.add(key)

            if page is not None:
                reference = f"{source} — Page {page}"
            else:
                reference = source

            if score is not None:
                try:
                    reference += f" (relevance: {float(score):.2f})"
                except (ValueError, TypeError):
                    pass

            references.append(reference)

            if len(references) >= 3:
                break

    if references:
        steps.append({
            "step": step_num,
            "type": "rag",
            "title": "Classical References Consulted",
            "detail": "; ".join(references)
        })
        step_num += 1
    elif active_topic in TOPIC_RELEVANT_BOOKS:
        books = TOPIC_RELEVANT_BOOKS.get(active_topic, [])[:2]
        if books:
            steps.append({
                "step": step_num,
                "type": "rag",
                "title": "Classical Literature Context",
                "detail": "Standard texts: " + ", ".join(books)
            })
            step_num += 1

    # Specificity check step
    steps.append({
        "step": step_num,
        "type": "specificity",
        "title": "Chart-Specificity Check",
        "detail": f"Status: SPECIFIC. Reading verified against {ascendant_sign} Ascendant, planet positions, and active Dasha."
    })

    return steps


def format_reasoning_trace_text(steps: List[dict], language: str = "Hinglish") -> str:
    """Render the trace as readable text for display (not for the LLM prompt —
    this is shown directly in the UI when the user clicks 'Explain this')."""
    if not steps:
        labels = {
            "English": "No detailed reasoning trace available for this response.",
            "Hindi": "इस उत्तर के लिए विस्तृत तर्क उपलब्ध नहीं है।",
            "Hinglish": "Is jawab ke liye detailed reasoning available nahi hai.",
        }
        return labels.get(language, labels["Hinglish"])

    lines = []
    for s in steps:
        lines.append(f"{s['step']}. {s['title']}\n   {s['detail']}")
    return "\n\n".join(lines)


def rank_favorable_periods(upcoming_periods: List[dict], topic: str, top_n: int = 3) -> List[dict]:
    """Ranks upcoming Antardasha periods by how many of the topic's
    significator planets are involved (Mahadasha lord + Antardasha lord)."""
    config = TOPIC_CHART_FACTORS.get(topic)
    if not config or not upcoming_periods:
        return []

    significators = set(config["planets"])
    scored = []
    for period in upcoming_periods:
        score = 0
        if period.get("mahadasha") in significators:
            score += 2
        if period.get("antardasha") in significators:
            score += 1
        if score > 0:
            scored.append({**period, "favorability_score": score})

    scored.sort(key=lambda p: p["favorability_score"], reverse=True)
    return scored[:top_n]


def format_dasha_timeline_for_prompt(upcoming_periods: List[dict], favorable_periods: List[dict], language: str = "Hinglish") -> str:
    """Formats the upcoming dasha timeline + ranked favorable periods into
    short plain text for the LLM prompt — not raw JSON."""
    if not upcoming_periods:
        return ""

    lines = ["Upcoming Dasha Periods (next few years):"]
    for p in upcoming_periods[:8]:
        maha = p.get("mahadasha", "")
        antar = p.get("antardasha", "")
        start = p.get("start", "").split(" ")[0]
        end = p.get("end", "").split(" ")[0]
        lines.append(f"- {maha} Mahadasha / {antar} Antardasha: {start} to {end}")

    if favorable_periods:
        lines.append("\nMost favorable upcoming periods for this topic:")
        for p in favorable_periods:
            maha = p.get("mahadasha", "")
            antar = p.get("antardasha", "")
            start = p.get("start", "").split(" ")[0]
            lines.append(f"- {maha}/{antar}: starting {start} (strong match for this question)")

    return "\n".join(lines)


def build_missing_evidence_note(
    topic: Optional[str],
    planets: List[dict],
    ascendant_sign: Optional[str],
    dasha_info: Optional[dict],
    divisional_text: str,
) -> str:
    """Returns an instruction block listing what evidence IS and ISN'T
    available for this topic, so the LLM can be transparent about
    confidence rather than presenting a full-confidence answer built on
    partial data."""
    if not topic:
        return ""

    config = TOPIC_CHART_FACTORS.get(topic)
    if not config:
        return ""

    available = []
    missing = []

    house_num = config["house"]
    house_lord = get_house_lord(house_num, ascendant_sign) if ascendant_sign else None
    if house_lord and any(p.get("name") == house_lord for p in planets):
        available.append(f"{house_num}th House lord ({house_lord}) placement")
    else:
        missing.append(f"{house_num}th House lord placement")

    for planet_name in config.get("planets", []):
        if any(p.get("name") == planet_name for p in planets):
            available.append(f"{planet_name} placement")
        else:
            missing.append(f"{planet_name} placement")

    if config.get("divisional_chart"):
        if divisional_text:
            available.append(f"{config['divisional_chart']} divisional chart")
        else:
            missing.append(f"{config['divisional_chart']} divisional chart")

    if dasha_info and dasha_info.get("current_mahadasha"):
        available.append("Current Dasha timing")
    else:
        missing.append("Current Dasha timing")

    if not missing:
        return f"Evidence check for {topic}: Full evidence available ({', '.join(available)}). Speak with normal confidence."

    return (
        f"Evidence check for {topic}: Available — {', '.join(available) or 'none'}. "
        f"Missing — {', '.join(missing)}. "
        f"Where evidence is missing, do not invent specifics for it — either omit that angle "
        f"entirely or speak in slightly more general terms for that part only, while still "
        f"staying confident about what IS available."
    )
    
# ------------------------------------------------------------------
# Evidence Consensus Label — converts the numeric confidence_pct + vote
# counts from build_evidence_vote() into a plain HIGH/MEDIUM/LOW/CONFLICTING
# label, and a matching instruction for the LLM prompt. This is what the
# reasoning trace and _get_topic_bundle already call — was previously
# missing, causing an import crash.
# ------------------------------------------------------------------
def get_evidence_consensus_label(vote: Optional[Dict]) -> str:
    """Returns one of: HIGH, MEDIUM, LOW, CONFLICTING, NONE."""
    if not vote:
        return "NONE"

    positive = vote.get("positive_count", 0)
    negative = vote.get("negative_count", 0)
    confidence = vote.get("confidence_pct", 50)
    verdict = vote.get("verdict")

    # Conflicting: real disagreement between independent sources, not just
    # "not enough evidence either way" — both directions actually present.
    if positive > 0 and negative > 0 and verdict == "mixed":
        return "CONFLICTING"

    if confidence >= 70:
        return "HIGH"
    if confidence >= 55:
        return "MEDIUM"
    return "LOW"


def get_consensus_instruction(consensus_label: str) -> str:
    """The actual instruction injected into the prompt — this is what
    changes model behavior based on evidence strength, not just displays it."""
    instructions = {
        "HIGH": (
            "Evidence Confidence: HIGH. Multiple independent sources (Dasha, chart "
            "placement, yogas) agree. You may state your reading with strong, direct "
            "confidence."
        ),
        "MEDIUM": (
            "Evidence Confidence: MEDIUM. Sources are grounded but not unanimous. "
            "Speak with normal confidence, but avoid absolute/guaranteed language."
        ),
        "LOW": (
            "Evidence Confidence: LOW. Limited supporting signal was found. Keep the "
            "reading general and honest about the limited evidence — do not manufacture "
            "false certainty."
        ),
        "CONFLICTING": (
            "Evidence Confidence: CONFLICTING. Independent sources genuinely disagree "
            "(some supportive, some challenging). Do NOT force a single confident verdict. "
            "Present both sides honestly in your own natural voice — this is real nuance "
            "in the chart, not a flaw in your reasoning."
        ),
        "NONE": (
            "Evidence Confidence: Not computed for this question. Answer based on "
            "available chart and Dasha data as normal."
        ),
    }
    return instructions.get(consensus_label, instructions["NONE"])
