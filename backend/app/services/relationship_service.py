"""
Relationship-Aware Astrological Context Engine
Adapts the astrologer's lens, house focus, prompt guidance,
and starter FAQ suggestions based on the active profile's relation tag.
"""
from typing import Dict, List, Optional


RELATION_CONFIGS: Dict[str, Dict] = {
    "Child": {
        "emoji": "👶",
        "lens": "Guardian/Parent Consultation",
        "age_context": "This is a chart reading for a child/minor — provide guidance from a supportive parental perspective.",
        "tone_instruction": (
            "Speak as if advising a concerned, loving parent or guardian about their child's natural gifts, "
            "potential, health, and education. Do NOT address the child directly — address the parent/guardian. "
            "Focus on nurturing, encouragement, and practical parenting guidance. "
            "Avoid adult themes (marriage, romantic relationships, alcohol, debt, corporate politics)."
        ),
        "priority_houses": [1, 4, 5, 6],
        "priority_planets": ["Moon", "Mercury", "Jupiter", "Sun"],
        "house_themes": {
            1: "physical constitution and vitality",
            4: "foundational learning environment and home support",
            5: "intellect, creativity, grasping power, and natural talents",
            6: "immunity, health, and daily routine",
        },
        "prompt_guidance": (
            "RELATIONSHIP CONTEXT — CHILD PROFILE:\n"
            "This chart belongs to a child. Prioritize the 5th house (intellect & grasping power), "
            "4th house (learning environment & foundational security), and 1st/6th houses (physical health & immunity). "
            "Key planets to weigh: Mercury (logic & memory), Jupiter (wisdom & learning), Moon (emotional security). "
            "Guidance should help the parent/guardian understand: natural study strengths, favorable exam periods, "
            "recommended learning styles, concentration tips, and health/immunity patterns."
        ),
    },

    "Partner": {
        "emoji": "❤️",
        "lens": "Relationship/Spouse Consultation",
        "age_context": "This is a chart reading for a romantic partner or spouse.",
        "tone_instruction": (
            "Speak as if advising about shared relationship dynamics and joint life goals. "
            "Balance individual personality insights with how this person complements or challenges the user. "
            "Focus on relationship harmony, communication, shared finances, and mutual growth."
        ),
        "priority_houses": [2, 7, 8, 11],
        "priority_planets": ["Venus", "Jupiter", "Mars", "Moon"],
        "house_themes": {
            2: "shared family wealth and financial values",
            7: "partnership dynamics, compatibility, and relationship harmony",
            8: "deep emotional bonding and joint financial transformation",
            11: "shared aspirations, social circles, and mutual gains",
        },
        "prompt_guidance": (
            "RELATIONSHIP CONTEXT — PARTNER/SPOUSE PROFILE:\n"
            "This chart belongs to the user's romantic partner or spouse. Prioritize the 7th house (partnership harmony), "
            "2nd and 11th houses (shared wealth and mutual gains), and 8th house (emotional depth and bonding). "
            "Key planets to weigh: Venus (love & harmony), Jupiter (growth in relationship), Mars (passion & temperament). "
            "Guidance should address: relationship compatibility insights, communication strengths and friction points, "
            "favorable periods for joint decisions (investments, property, family), and emotional compatibility."
        ),
    },

    "Mother": {
        "emoji": "🌸",
        "lens": "Maternal Elder Consultation",
        "age_context": "This is a chart reading for the user's mother — an elder female family member.",
        "tone_instruction": (
            "Speak with deep respect and reverence. Focus primarily on health, wellness, emotional peace of mind, "
            "family harmony, and spiritual life. Address relevant periods for pilgrimage, meditation, and spiritual retreats. "
            "Avoid aggressive achievement-oriented framing — emphasize peace, contentment, and graceful aging."
        ),
        "priority_houses": [1, 4, 6, 9, 12],
        "priority_planets": ["Moon", "Sun", "Jupiter", "Saturn"],
        "house_themes": {
            1: "overall physical health and vitality",
            4: "domestic harmony and comfort in later life",
            6: "chronic health patterns and medical care timing",
            9: "spirituality, pilgrimage, and dharma",
            12: "spiritual liberation, peace of mind, and rest",
        },
        "prompt_guidance": (
            "RELATIONSHIP CONTEXT — MOTHER PROFILE:\n"
            "This chart belongs to the user's mother. Prioritize the 6th house (health & medical care), "
            "9th house (spirituality, pilgrimage, Teertha Yatra), 12th house (spiritual peace, rest, surrender), "
            "and 4th house (domestic harmony and comfort). "
            "Key planets: Moon (emotional health), Sun (vitality), Jupiter (blessings & grace), Saturn (aging & discipline). "
            "Guidance should cover: current health patterns and precautions, favorable timing for pilgrimages or spiritual retreats, "
            "family harmony and domestic peace, and emotional/mental well-being."
        ),
    },

    "Father": {
        "emoji": "🌟",
        "lens": "Paternal Elder Consultation",
        "age_context": "This is a chart reading for the user's father — an elder male family member.",
        "tone_instruction": (
            "Speak with deep respect. Focus on health longevity, financial legacy, professional recognition, "
            "spiritual growth, and family leadership. Address practical concerns around retirement, investments, "
            "and health patterns. Be practical and grounded."
        ),
        "priority_houses": [1, 6, 9, 10, 11],
        "priority_planets": ["Sun", "Jupiter", "Saturn", "Mars"],
        "house_themes": {
            1: "physical health and overall vitality",
            6: "health management and overcoming obstacles",
            9: "wisdom, dharma, and spiritual growth",
            10: "professional legacy and social recognition",
            11: "financial gains and retirement stability",
        },
        "prompt_guidance": (
            "RELATIONSHIP CONTEXT — FATHER PROFILE:\n"
            "This chart belongs to the user's father. Prioritize the 6th house (health & longevity management), "
            "9th house (spiritual life, religious activities, pilgrimage), 10th house (professional recognition & legacy), "
            "and 11th house (financial stability and gains). "
            "Key planets: Sun (vitality & authority), Jupiter (wisdom), Saturn (structure & discipline), Mars (energy). "
            "Guidance should address: health maintenance and warning periods, retirement and financial stability insights, "
            "favorable spiritual periods, and legacy or family leadership themes."
        ),
    },

    "Friend": {
        "emoji": "🤝",
        "lens": "Friend/Social Circle Consultation",
        "age_context": "This is a chart reading for a friend.",
        "tone_instruction": (
            "Speak in a warm, peer-to-peer, approachable tone. Cover all life areas equally. "
            "Can include friendship dynamics, social circles, and shared experiences."
        ),
        "priority_houses": [1, 3, 5, 7, 10, 11],
        "priority_planets": ["Mercury", "Jupiter", "Venus", "Moon"],
        "house_themes": {
            3: "communication, social skills, and short trips",
            5: "creativity, fun, and romantic inclinations",
            11: "social gains, friendships, and aspirations",
        },
        "prompt_guidance": (
            "RELATIONSHIP CONTEXT — FRIEND PROFILE:\n"
            "This chart belongs to a friend of the user. Take a balanced, life-spanning approach covering career, "
            "relationships, social life, and personal growth. "
            "Key planets: Mercury (social communication), Jupiter (fortune), Venus (social charm), Moon (emotional nature). "
            "Tone should feel warm, peer-like, and conversational — not overly formal."
        ),
    },

    "Self": {
        "emoji": "✨",
        "lens": "Personal Consultation",
        "age_context": "This is the user's own personal chart reading.",
        "tone_instruction": (
            "Speak directly and personally to the user. Cover all life areas comprehensively — career, relationships, "
            "health, finances, spirituality, and personal growth — based on what they ask."
        ),
        "priority_houses": [1, 5, 7, 9, 10, 11],
        "priority_planets": ["Sun", "Moon", "Jupiter", "Saturn"],
        "house_themes": {},
        "prompt_guidance": (
            "RELATIONSHIP CONTEXT — SELF/PERSONAL PROFILE:\n"
            "This is the user's own chart. Provide fully personalized, direct, first-person astrological guidance. "
            "Cover any life area they ask about with full depth and confidence."
        ),
    },

    "Other": {
        "emoji": "👤",
        "lens": "General Consultation",
        "age_context": "This is a chart reading for someone in the user's life.",
        "tone_instruction": "Speak with a balanced, observational tone covering all life areas.",
        "priority_houses": [1, 5, 7, 10, 11],
        "priority_planets": ["Sun", "Moon", "Jupiter"],
        "house_themes": {},
        "prompt_guidance": (
            "RELATIONSHIP CONTEXT — OTHER PROFILE:\n"
            "This is a chart for someone in the user's life. Provide balanced astrological insights. "
            "Let the user's specific questions guide the focus area."
        ),
    },
}


def get_relationship_context(
    relation: Optional[str],
    name: Optional[str] = "this person",
    language: str = "English"
) -> Dict:
    """Returns full relationship context dict for prompt injection and FAQ rendering."""
    key = (relation or "Self").strip().capitalize()
    config = RELATION_CONFIGS.get(key, RELATION_CONFIGS["Self"])

    prompt_guidance = config["prompt_guidance"]
    prompt_guidance += f"\nConsultation is for: {name or 'this person'} (Relation: {key})."

    return {
        "relation": key,
        "emoji": config["emoji"],
        "lens": config["lens"],
        "prompt_guidance": prompt_guidance,
        "tone_instruction": config["tone_instruction"],
        "priority_houses": config["priority_houses"],
        "priority_planets": config["priority_planets"],
        "house_themes": config["house_themes"],
    }


def get_relationship_faqs(relation: Optional[str], language: str = "English") -> List[Dict]:
    """Returns relationship-specific FAQ categories and questions for the FaqStarter UI."""
    key = (relation or "Self").strip().capitalize()

    faqs: Dict[str, Dict[str, List[Dict]]] = {
        "Child": {
            "English": [
                {"label": "Studies & Talent", "emoji": "📚", "questions": [
                    "Which subject or stream will suit them best?",
                    "When are the most favorable periods for exams and studies?",
                    "What are their strongest natural talents and skills?",
                ]},
                {"label": "Health & Immunity", "emoji": "🌿", "questions": [
                    "What health patterns should we watch out for?",
                    "How can we strengthen their immunity and energy?",
                    "When are favorable periods for their overall health?",
                ]},
                {"label": "Focus & Concentration", "emoji": "🎯", "questions": [
                    "How can we improve their focus and memory?",
                    "What kind of learning environment suits their chart best?",
                    "Are there remedies to strengthen Mercury for better grasping?",
                ]},
                {"label": "Career Potential", "emoji": "🌟", "questions": [
                    "What career fields are naturally aligned with their chart?",
                    "Is there an indication of arts, science, or commerce in their chart?",
                    "What unique strengths will help them succeed?",
                ]},
            ],
            "Hindi": [
                {"label": "पढ़ाई और प्रतिभा", "emoji": "📚", "questions": [
                    "इनके लिए कौन सा विषय या स्ट्रीम सबसे अच्छा रहेगा?",
                    "परीक्षा के लिए सबसे अनुकूल समय कब है?",
                    "इनकी सबसे बड़ी प्राकृतिक प्रतिभा क्या है?",
                ]},
                {"label": "स्वास्थ्य", "emoji": "🌿", "questions": [
                    "स्वास्थ्य के बारे में क्या सावधानी रखें?",
                    "रोग प्रतिरोधक शक्ति कैसे बढ़ाएं?",
                    "कब का समय स्वास्थ्य के लिए अच्छा रहेगा?",
                ]},
            ],
            "Hinglish": [
                {"label": "Studies & Talent", "emoji": "📚", "questions": [
                    "Inke liye konsa subject ya stream best rahega?",
                    "Exams ke liye sabse acha time kab hai?",
                    "Inki sabse badi natural talent kya hai?",
                ]},
                {"label": "Health", "emoji": "🌿", "questions": [
                    "Health mein kya dhyan rakhna chahiye?",
                    "Immunity kaise strengthen karein?",
                    "Kab ka samay inke liye healthy rahega?",
                ]},
            ],
        },

        "Partner": {
            "English": [
                {"label": "Relationship Harmony", "emoji": "❤️", "questions": [
                    "How is the harmony and understanding in this relationship?",
                    "What are the biggest strengths and challenges between us?",
                    "When are the most favorable periods for our relationship?",
                ]},
                {"label": "Joint Wealth & Finance", "emoji": "💰", "questions": [
                    "How does their chart support our joint financial decisions?",
                    "When are the best times for joint investments or property?",
                    "How is their 11th house for shared gains and aspirations?",
                ]},
                {"label": "Career & Ambition", "emoji": "💼", "questions": [
                    "What career path aligns best with their chart?",
                    "When are their most favorable professional growth periods?",
                    "How can we best support each other's career goals?",
                ]},
                {"label": "Communication & Temperament", "emoji": "💬", "questions": [
                    "How does their Mars and Mercury shape their communication style?",
                    "What triggers stress or conflict for them astrologically?",
                    "How can we communicate more smoothly as partners?",
                ]},
            ],
            "Hindi": [
                {"label": "रिश्ते की समझ", "emoji": "❤️", "questions": [
                    "रिश्ते में तालमेल कैसा रहेगा?",
                    "हमारे बीच सबसे बड़ी ताकत और चुनौती क्या है?",
                    "रिश्ते के लिए सबसे अच्छा समय कब है?",
                ]},
                {"label": "साझा धन", "emoji": "💰", "questions": [
                    "साझा निवेश और संपत्ति के लिए कब का समय अच्छा है?",
                    "इनकी कुंडली आर्थिक रूप से कैसी है?",
                ]},
            ],
            "Hinglish": [
                {"label": "Relationship", "emoji": "❤️", "questions": [
                    "Hamare rishte mein harmony kaisi rahegi?",
                    "Hamare beech sabse badi strength aur challenge kya hai?",
                    "Rishte ke liye sabse acha samay kab hai?",
                ]},
                {"label": "Joint Finance", "emoji": "💰", "questions": [
                    "Joint investment ke liye kaun sa samay best hai?",
                    "Inki financial stability kaisi hai?",
                ]},
            ],
        },

        "Mother": {
            "English": [
                {"label": "Health & Wellness", "emoji": "🌿", "questions": [
                    "How is her overall health and vitality looking this year?",
                    "What health patterns or areas should we watch out for?",
                    "When are the most favorable periods for her health and recovery?",
                ]},
                {"label": "Peace of Mind", "emoji": "🕊️", "questions": [
                    "How can we help bring more peace and contentment to her life?",
                    "What does her chart say about emotional and mental well-being?",
                    "Are there any astrological remedies for her mental peace?",
                ]},
                {"label": "Spirituality & Pilgrimage", "emoji": "🕉️", "questions": [
                    "When are the most favorable times for pilgrimage or Teertha Yatra?",
                    "Which spiritual practices or mantras are best aligned with her chart?",
                    "How is her 9th house for dharma and spiritual blessings?",
                ]},
                {"label": "Family Harmony", "emoji": "🏡", "questions": [
                    "How is the domestic harmony and family peace looking ahead?",
                    "What does her chart indicate about family relationships and support?",
                ]},
            ],
            "Hindi": [
                {"label": "स्वास्थ्य", "emoji": "🌿", "questions": [
                    "उनका स्वास्थ्य इस साल कैसा रहेगा?",
                    "स्वास्थ्य के लिए क्या सावधानी रखें?",
                    "ठीक होने का सबसे अच्छा समय कब है?",
                ]},
                {"label": "आध्यात्मिकता", "emoji": "🕉️", "questions": [
                    "तीर्थ यात्रा के लिए सबसे अच्छा समय कब है?",
                    "उनके लिए कौन सी साधना या मंत्र उचित है?",
                ]},
            ],
            "Hinglish": [
                {"label": "Health", "emoji": "🌿", "questions": [
                    "Unka swasthya is saal kaisa rahega?",
                    "Health ke liye kya savdhani rakhein?",
                    "Recovery ke liye sabse acha samay kab hai?",
                ]},
                {"label": "Spirituality", "emoji": "🕉️", "questions": [
                    "Teerth yatra ke liye sab se acha time kab hai?",
                    "Unke liye kaunsa mantra ya sadhana theek rahega?",
                ]},
            ],
        },

        "Father": {
            "English": [
                {"label": "Health & Longevity", "emoji": "💪", "questions": [
                    "How is his overall health and energy looking this year?",
                    "What health areas should we be attentive to?",
                    "When are the most favorable periods for his health?",
                ]},
                {"label": "Financial Stability", "emoji": "💰", "questions": [
                    "How is his financial stability and retirement planning looking?",
                    "Are there favorable periods for financial gains or property?",
                    "What does his 11th house indicate for income and gains?",
                ]},
                {"label": "Spirituality & Wisdom", "emoji": "🕉️", "questions": [
                    "What does his chart say about spiritual growth and dharma?",
                    "When are favorable times for pilgrimage or religious activities?",
                    "How can he find more meaning and purpose in this phase of life?",
                ]},
                {"label": "Legacy & Recognition", "emoji": "🌟", "questions": [
                    "What professional legacy or achievement is indicated in his chart?",
                    "How is his 10th house for social standing and recognition?",
                ]},
            ],
            "Hindi": [
                {"label": "स्वास्थ्य", "emoji": "💪", "questions": [
                    "उनका स्वास्थ्य इस साल कैसा रहेगा?",
                    "किस चीज़ का ध्यान रखना ज़रूरी है?",
                ]},
                {"label": "आर्थिक स्थिरता", "emoji": "💰", "questions": [
                    "आर्थिक स्थिरता और निवेश के लिए कब का समय अच्छा है?",
                    "संपत्ति के योग कब बन रहे हैं?",
                ]},
            ],
            "Hinglish": [
                {"label": "Health", "emoji": "💪", "questions": [
                    "Unka swasthya is saal kaisa rahega?",
                    "Kya dhyan rakhna zaroori hai?",
                ]},
                {"label": "Finance", "emoji": "💰", "questions": [
                    "Financial stability aur investment ke liye kab ka samay acha hai?",
                    "Property ke yog kab ban rahe hain?",
                ]},
            ],
        },
    }

    # Self, Friend, Other fall back to the standard language-specific full FAQ
    relation_faqs = faqs.get(key)
    if not relation_faqs:
        return []  # Empty → FaqStarter uses default full FAQ categories

    return relation_faqs.get(language, relation_faqs.get("English", []))


relationship_service_instance = True  # Sentinel for import checks
