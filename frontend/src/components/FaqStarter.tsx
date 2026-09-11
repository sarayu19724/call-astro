import React, { useState } from 'react';

interface FaqStarterProps {
  onSelect: (question: string) => void;
  disabled: boolean;
  language: string;
  relation?: string;
  profileName?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Standard FAQ categories (used for Self / Friend / Other)
// ─────────────────────────────────────────────────────────────────────────────
const FAQ_CATEGORIES: Record<string, { label: string; emoji: string; questions: string[] }[]> = {
  English: [
    { label: 'Marriage', emoji: '💍', questions: ['When will I get married?', 'Will it be love or arranged marriage?', 'When will I have children?'] },
    { label: 'Love & Ex', emoji: '❤️', questions: ['Will my ex come back?', "What's my love life future?", 'When will I find my soulmate?'] },
    { label: 'Career & Job', emoji: '💼', questions: ['When will I get a job?', 'When will I get a promotion?', 'Which career is best for me?'] },
    { label: 'Finance', emoji: '💰', questions: ['Will my business succeed?', 'When will I become financially stable?', 'Is this a good time to invest?'] },
    { label: 'Abroad', emoji: '🌍', questions: ['Will I go abroad?', 'Is settlement abroad in my chart?', 'Which country is best for me?'] },
    { label: 'Health', emoji: '🏥', questions: ['How is my health this year?', 'What health issues should I watch?', 'When will my health improve?'] },
    { label: 'Remedies', emoji: '🪬', questions: ['Which gemstone should I wear?', 'What are the remedies for my problems?', 'Which day is lucky for me?'] },
  ],
  Hindi: [
    { label: 'विवाह', emoji: '💍', questions: ['मेरी शादी कब होगी?', 'प्रेम विवाह होगा या अरेंज?', 'संतान कब होगी?'] },
    { label: 'प्रेम', emoji: '❤️', questions: ['क्या वो वापस आएंगे?', 'मेरे प्रेम जीवन का भविष्य?', 'मुझे सच्चा प्यार कब मिलेगा?'] },
    { label: 'करियर', emoji: '💼', questions: ['नौकरी कब मिलेगी?', 'प्रमोशन कब होगा?', 'मेरे लिए कौन सा करियर अच्छा है?'] },
    { label: 'वित्त', emoji: '💰', questions: ['व्यापार में सफलता मिलेगी?', 'आर्थिक स्थिति कब सुधरेगी?', 'निवेश का सही समय क्या है?'] },
    { label: 'विदेश', emoji: '🌍', questions: ['क्या मैं विदेश जाऊंगा?', 'विदेश में बसने के योग हैं?', 'कौन सा देश मेरे लिए अच्छा है?'] },
    { label: 'स्वास्थ्य', emoji: '🏥', questions: ['इस साल स्वास्थ्य कैसा रहेगा?', 'किस बीमारी से सावधान रहूं?', 'स्वास्थ्य कब सुधरेगा?'] },
    { label: 'उपाय', emoji: '🪬', questions: ['कौन सा रत्न पहनूं?', 'समस्याओं के क्या उपाय हैं?', 'मेरा भाग्यशाली दिन कौन सा है?'] },
  ],
  Hinglish: [
    { label: 'Marriage', emoji: '💍', questions: ['Shadi kab hogi meri?', 'Love ya arranged marriage hogi?', 'Bacche kab honge?'] },
    { label: 'Love & Ex', emoji: '❤️', questions: ['Kya woh wapas aayenge?', 'Mera love life kaisa rahega?', 'Soulmate kab milega?'] },
    { label: 'Career & Job', emoji: '💼', questions: ['Job kab milegi?', 'Promotion kab milega?', 'Konsa career mujhe suit karega?'] },
    { label: 'Finance', emoji: '💰', questions: ['Business mein safalta milegi?', 'Paisa kab aayega?', 'Invest karne ka sahi time kya hai?'] },
    { label: 'Abroad', emoji: '🌍', questions: ['Kya main abroad jaunga?', 'Videsh mein settle hone ke chances hain?', 'Kaun sa desh mujhe suit karega?'] },
    { label: 'Health', emoji: '🏥', questions: ['Is saal sehat kaisi rahegi?', 'Kis bimari se bachna chahiye?', 'Sehat kab sudhrega?'] },
    { label: 'Remedies', emoji: '🪬', questions: ['Kaunsa gemstone pehnu?', 'Problems ke kya upay hain?', 'Mera lucky day kaunsa hai?'] },
  ],
};

// ─────────────────────────────────────────────────────────────────────────────
// Muhurta finder events
// ─────────────────────────────────────────────────────────────────────────────
const MUHURTA_EVENTS: Record<string, { label: string; emoji: string }[]> = {
  English: [
    { label: 'Marriage', emoji: '💍' },
    { label: 'Business Opening', emoji: '🏪' },
    { label: 'House Warming', emoji: '🏠' },
    { label: 'Travel / Yatra', emoji: '✈️' },
    { label: 'Vehicle Purchase', emoji: '🚗' },
    { label: 'Surgery', emoji: '🏥' },
    { label: 'Starting Studies', emoji: '📚' },
    { label: 'Job Interview', emoji: '💼' },
  ],
  Hindi: [
    { label: 'विवाह', emoji: '💍' },
    { label: 'व्यापार शुरू', emoji: '🏪' },
    { label: 'गृह प्रवेश', emoji: '🏠' },
    { label: 'यात्रा', emoji: '✈️' },
    { label: 'वाहन खरीद', emoji: '🚗' },
    { label: 'शल्य चिकित्सा', emoji: '🏥' },
    { label: 'पढ़ाई शुरू', emoji: '📚' },
    { label: 'नौकरी इंटरव्यू', emoji: '💼' },
  ],
  Hinglish: [
    { label: 'Shaadi', emoji: '💍' },
    { label: 'Business Shuru', emoji: '🏪' },
    { label: 'Griha Pravesh', emoji: '🏠' },
    { label: 'Travel / Yatra', emoji: '✈️' },
    { label: 'Gaadi Kharidna', emoji: '🚗' },
    { label: 'Operation', emoji: '🏥' },
    { label: 'Padhai Shuru', emoji: '📚' },
    { label: 'Job Interview', emoji: '💼' },
  ],
};

// ─────────────────────────────────────────────────────────────────────────────
// Relationship-specific FAQ data (mirrors relationship_service.py)
// ─────────────────────────────────────────────────────────────────────────────
const RELATION_ICONS: Record<string, string> = {
  Child: '👶',
  Partner: '❤️',
  Mother: '🌸',
  Father: '🌟',
  Friend: '🤝',
  Self: '✨',
  Other: '👤',
};

const RELATION_FAQS: Record<string, Record<string, { label: string; emoji: string; questions: string[] }[]>> = {
  Child: {
    English: [
      { label: 'Studies & Talent', emoji: '📚', questions: [
        'Which subject or stream will suit them best?',
        'When are the most favorable periods for exams and studies?',
        'What are their strongest natural talents and skills?',
      ]},
      { label: 'Health & Immunity', emoji: '🌿', questions: [
        'What health patterns should we watch out for?',
        'How can we strengthen their immunity and energy?',
        'When are favorable periods for their overall health?',
      ]},
      { label: 'Focus & Memory', emoji: '🎯', questions: [
        'How can we improve their focus and concentration?',
        'What kind of learning environment suits their chart best?',
        'Are there remedies to strengthen Mercury for better grasping?',
      ]},
      { label: 'Career Potential', emoji: '🌟', questions: [
        'What career fields are naturally aligned with their chart?',
        'Is there an indication of arts, science, or commerce in their chart?',
        'What unique strengths will help them succeed?',
      ]},
    ],
    Hindi: [
      { label: 'पढ़ाई और प्रतिभा', emoji: '📚', questions: [
        'इनके लिए कौन सा विषय या स्ट्रीम सबसे अच्छा रहेगा?',
        'परीक्षा के लिए सबसे अनुकूल समय कब है?',
        'इनकी सबसे बड़ी प्राकृतिक प्रतिभा क्या है?',
      ]},
      { label: 'स्वास्थ्य', emoji: '🌿', questions: [
        'स्वास्थ्य के बारे में क्या सावधानी रखें?',
        'रोग प्रतिरोधक शक्ति कैसे बढ़ाएं?',
        'स्वास्थ्य के लिए अनुकूल समय कब है?',
      ]},
      { label: 'एकाग्रता', emoji: '🎯', questions: [
        'इनकी एकाग्रता और स्मरण शक्ति कैसे बढ़ाएं?',
        'इनके लिए सबसे अच्छा सीखने का माहौल कैसा हो?',
        'बुद्धि बढ़ाने के लिए क्या उपाय हैं?',
      ]},
      { label: 'करियर संभावना', emoji: '🌟', questions: [
        'इनके लिए कौन सा करियर अच्छा रहेगा?',
        'इनकी कुंडली में कला, विज्ञान या वाणिज्य के योग हैं?',
      ]},
    ],
    Hinglish: [
      { label: 'Studies & Talent', emoji: '📚', questions: [
        'Inke liye konsa subject ya stream best rahega?',
        'Exams ke liye sabse acha time kab hai?',
        'Inki sabse badi natural talent kya hai?',
      ]},
      { label: 'Health', emoji: '🌿', questions: [
        'Health mein kya dhyan rakhna chahiye?',
        'Immunity kaise strengthen karein?',
        'Kab ka samay inke liye healthy rahega?',
      ]},
      { label: 'Focus & Memory', emoji: '🎯', questions: [
        'Focus aur yaaddaasht kaise badhayein?',
        'Inke liye kaisa learning environment best hai?',
        'Mercury strengthen karne ke kya upaay hain?',
      ]},
      { label: 'Career', emoji: '🌟', questions: [
        'Inke liye kaun sa career aligned hai?',
        'Inki kundli mein art, science ya commerce ke yog hain?',
      ]},
    ],
  },

  Partner: {
    English: [
      { label: 'Relationship Harmony', emoji: '❤️', questions: [
        'How is the harmony and understanding in this relationship?',
        'What are the biggest strengths and challenges between us?',
        'When are the most favorable periods for our relationship?',
      ]},
      { label: 'Joint Wealth & Finance', emoji: '💰', questions: [
        'How does their chart support our joint financial decisions?',
        'When are the best times for joint investments or property?',
        'How is their 11th house for shared gains and aspirations?',
      ]},
      { label: 'Career & Ambition', emoji: '💼', questions: [
        'What career path aligns best with their chart?',
        'When are their most favorable professional growth periods?',
        "How can we best support each other's career goals?",
      ]},
      { label: 'Communication Style', emoji: '💬', questions: [
        'How does their Mars and Mercury shape their communication style?',
        'What triggers stress or conflict for them astrologically?',
        'How can we communicate more smoothly as partners?',
      ]},
    ],
    Hindi: [
      { label: 'रिश्ते की समझ', emoji: '❤️', questions: [
        'रिश्ते में तालमेल कैसा रहेगा?',
        'हमारे बीच सबसे बड़ी ताकत और चुनौती क्या है?',
        'रिश्ते के लिए सबसे अच्छा समय कब है?',
      ]},
      { label: 'साझा धन', emoji: '💰', questions: [
        'साझा निवेश और संपत्ति के लिए कब का समय अच्छा है?',
        'इनकी कुंडली आर्थिक रूप से कैसी है?',
      ]},
      { label: 'करियर और महत्वाकांक्षा', emoji: '💼', questions: [
        'इनके लिए कौन सा करियर सबसे अच्छा है?',
        'इनके लिए सबसे अनुकूल पेशेवर समय कब है?',
      ]},
      { label: 'संवाद शैली', emoji: '💬', questions: [
        'इनका संवाद करने का तरीका कैसा है?',
        'रिश्ते में टकराव कम करने के उपाय क्या हैं?',
      ]},
    ],
    Hinglish: [
      { label: 'Relationship', emoji: '❤️', questions: [
        'Hamare rishte mein harmony kaisi rahegi?',
        'Hamare beech sabse badi strength aur challenge kya hai?',
        'Rishte ke liye sabse acha samay kab hai?',
      ]},
      { label: 'Joint Finance', emoji: '💰', questions: [
        'Joint investment ke liye kaun sa samay best hai?',
        'Inki financial stability kaisi hai?',
      ]},
      { label: 'Career', emoji: '💼', questions: [
        'Inke career ke liye sabse acha time kab hai?',
        'Ek dusre ke goals ko support kaise karein?',
      ]},
      { label: 'Communication', emoji: '💬', questions: [
        'Inki communication style kaisi hai?',
        'Rishte mein conflict kam karne ke upay kya hain?',
      ]},
    ],
  },

  Mother: {
    English: [
      { label: 'Health & Wellness', emoji: '🌿', questions: [
        'How is her overall health and vitality looking this year?',
        'What health patterns or areas should we watch out for?',
        'When are the most favorable periods for her health and recovery?',
      ]},
      { label: 'Peace of Mind', emoji: '🕊️', questions: [
        'How can we help bring more peace and contentment to her life?',
        'What does her chart say about emotional and mental well-being?',
        'Are there any astrological remedies for her mental peace?',
      ]},
      { label: 'Spirituality & Pilgrimage', emoji: '🕉️', questions: [
        'When are the most favorable times for pilgrimage or Teertha Yatra?',
        'Which spiritual practices or mantras are best aligned with her chart?',
        'How is her 9th house for dharma and spiritual blessings?',
      ]},
      { label: 'Family Harmony', emoji: '🏡', questions: [
        'How is the domestic harmony and family peace looking ahead?',
        'What does her chart indicate about family relationships and support?',
      ]},
    ],
    Hindi: [
      { label: 'स्वास्थ्य', emoji: '🌿', questions: [
        'उनका स्वास्थ्य इस साल कैसा रहेगा?',
        'स्वास्थ्य के लिए क्या सावधानी रखें?',
        'स्वस्थ होने का सबसे अच्छा समय कब है?',
      ]},
      { label: 'मन की शांति', emoji: '🕊️', questions: [
        'उनके जीवन में शांति और संतोष कैसे बढ़ाएं?',
        'मानसिक स्वास्थ्य के लिए क्या उपाय करें?',
      ]},
      { label: 'आध्यात्मिकता', emoji: '🕉️', questions: [
        'तीर्थ यात्रा के लिए सबसे अच्छा समय कब है?',
        'उनके लिए कौन सी साधना या मंत्र उचित है?',
      ]},
      { label: 'पारिवारिक सुख', emoji: '🏡', questions: [
        'घर में शांति और सुख कब आएगा?',
        'परिवार के रिश्तों में क्या देखा जा रहा है?',
      ]},
    ],
    Hinglish: [
      { label: 'Health', emoji: '🌿', questions: [
        'Unka swasthya is saal kaisa rahega?',
        'Health ke liye kya savdhani rakhein?',
        'Recovery ke liye sabse acha samay kab hai?',
      ]},
      { label: 'Peace of Mind', emoji: '🕊️', questions: [
        'Unke liye shanti aur sukoon kaise laayen?',
        'Maansik swasthya ke liye kya upaay hain?',
      ]},
      { label: 'Spirituality', emoji: '🕉️', questions: [
        'Teerth yatra ke liye sabse acha time kab hai?',
        'Unke liye kaunsa mantra ya sadhana theek rahega?',
      ]},
      { label: 'Family Harmony', emoji: '🏡', questions: [
        'Ghar mein sukh-shanti kab aayegi?',
        'Pariwar ke rishton mein kya dikh raha hai?',
      ]},
    ],
  },

  Father: {
    English: [
      { label: 'Health & Longevity', emoji: '💪', questions: [
        'How is his overall health and energy looking this year?',
        'What health areas should we be attentive to?',
        'When are the most favorable periods for his health?',
      ]},
      { label: 'Financial Stability', emoji: '💰', questions: [
        'How is his financial stability and gains looking ahead?',
        'Are there favorable periods for financial gains or property?',
        'What does his 11th house indicate for income and stability?',
      ]},
      { label: 'Spirituality & Wisdom', emoji: '🕉️', questions: [
        'What does his chart say about spiritual growth and dharma?',
        'When are favorable times for pilgrimage or religious activities?',
        'How can he find more meaning and purpose in this life phase?',
      ]},
      { label: 'Legacy & Recognition', emoji: '🌟', questions: [
        'What professional legacy or achievement is indicated in his chart?',
        'How is his 10th house for social standing and recognition?',
      ]},
    ],
    Hindi: [
      { label: 'स्वास्थ्य', emoji: '💪', questions: [
        'उनका स्वास्थ्य इस साल कैसा रहेगा?',
        'किस चीज़ का ध्यान रखना ज़रूरी है?',
        'स्वास्थ्य के लिए कब का समय अनुकूल है?',
      ]},
      { label: 'आर्थिक स्थिरता', emoji: '💰', questions: [
        'आर्थिक स्थिरता और निवेश के लिए कब का समय अच्छा है?',
        'संपत्ति के योग कब बन रहे हैं?',
      ]},
      { label: 'आध्यात्मिकता', emoji: '🕉️', questions: [
        'उनके लिए आध्यात्मिक जीवन कैसा दिखता है?',
        'तीर्थ यात्रा के लिए शुभ समय कब है?',
      ]},
      { label: 'विरासत और मान-सम्मान', emoji: '🌟', questions: [
        'समाज में इनकी प्रतिष्ठा कैसी रहेगी?',
        'इनके करियर की विरासत क्या दिखती है?',
      ]},
    ],
    Hinglish: [
      { label: 'Health', emoji: '💪', questions: [
        'Unka swasthya is saal kaisa rahega?',
        'Kya dhyan rakhna zaroori hai?',
        'Sehat ke liye kab ka samay acha hai?',
      ]},
      { label: 'Finance', emoji: '💰', questions: [
        'Financial stability aur investment ke liye kab ka samay acha hai?',
        'Property ke yog kab ban rahe hain?',
      ]},
      { label: 'Spirituality', emoji: '🕉️', questions: [
        'Unka aatmik jeevan kaisa dikh raha hai?',
        'Teerth yatra ke liye shubh samay kab hai?',
      ]},
      { label: 'Legacy', emoji: '🌟', questions: [
        'Unki samajik pratishtha kaisi rahegi?',
        'Career ki virasat mein kya dikh raha hai?',
      ]},
    ],
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Muhurta finder panel
// ─────────────────────────────────────────────────────────────────────────────
const MuhurtaPanel: React.FC<{
  language: string;
  onSelect: (q: string) => void;
  onClose: () => void;
  disabled: boolean;
}> = ({ language, onSelect, onClose, disabled }) => {
  const lang = language in MUHURTA_EVENTS ? language : 'Hinglish';
  const events = MUHURTA_EVENTS[lang];
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');

  const handleFind = () => {
    if (!selectedEvent) return;
    let query = '';
    if (language === 'Hindi') {
      query = `${selectedEvent} के लिए सबसे शुभ मुहूर्त बताइए${fromDate ? `, ${fromDate} के बाद` : ''}${toDate ? ` और ${toDate} से पहले` : ''}। कृपया दिन, तिथि, नक्षत्र और राहु काल का ध्यान रखें।`;
    } else if (language === 'Hinglish') {
      query = `${selectedEvent} ke liye sabse shubh muhurta kab hai${fromDate ? `, ${fromDate} ke baad` : ''}${toDate ? ` aur ${toDate} se pehle` : ''}? Kripya din, tithi, nakshatra aur Rahu Kaal dhyan mein rakhein.`;
    } else {
      query = `What is the most auspicious Muhurta for ${selectedEvent}${fromDate ? ` after ${fromDate}` : ''}${toDate ? ` and before ${toDate}` : ''}? Please consider the best day (Vara), Tithi, Nakshatra, and avoid Rahu Kala.`;
    }
    onSelect(query);
    onClose();
  };

  const placeholder = language === 'Hindi' ? 'तिथि चुनें' : 'Select date';
  const findLabel   = language === 'Hindi' ? '🔍 मुहूर्त खोजें' : language === 'Hinglish' ? '🔍 Muhurta Dhundho' : '🔍 Find Muhurta';
  const fromLabel   = language === 'Hindi' ? 'इस तारीख से' : language === 'Hinglish' ? 'Is date ke baad' : 'From date (optional)';
  const toLabel     = language === 'Hindi' ? 'इस तारीख तक' : language === 'Hinglish' ? 'Is date tak' : 'To date (optional)';
  const eventLabel  = language === 'Hindi' ? 'कार्यक्रम चुनें:' : language === 'Hinglish' ? 'Event chunein:' : 'Select event:';

  return (
    <div className="mt-2 mb-2 p-3 rounded-2xl border border-amber-200 bg-amber-50 shadow-sm">
      <div className="flex items-center justify-between mb-2.5">
        <span className="text-xs font-semibold text-amber-800 flex items-center gap-1.5">
          🗓️ {language === 'Hindi' ? 'मुहूर्त खोजक' : 'Muhurta Finder'}
        </span>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xs leading-none">✕</button>
      </div>

      <p className="text-[10px] text-amber-700 font-semibold uppercase tracking-wide mb-1.5">{eventLabel}</p>
      <div className="flex flex-wrap gap-1.5 mb-3">
        {events.map(ev => (
          <button
            key={ev.label}
            onClick={() => setSelectedEvent(ev.label)}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs border transition-all font-medium
              ${selectedEvent === ev.label
                ? 'bg-amber-500 text-white border-amber-500'
                : 'bg-white text-amber-700 border-amber-300 hover:bg-amber-100'
              }`}
          >
            <span>{ev.emoji}</span>
            <span>{ev.label}</span>
          </button>
        ))}
      </div>

      <div className="flex gap-2 mb-3">
        <div className="flex-1">
          <label className="text-[10px] text-amber-700 font-medium block mb-0.5">{fromLabel}</label>
          <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} placeholder={placeholder}
            className="w-full text-xs border border-amber-200 rounded-lg px-2 py-1.5 bg-white text-slate-700 focus:outline-none focus:border-amber-400" />
        </div>
        <div className="flex-1">
          <label className="text-[10px] text-amber-700 font-medium block mb-0.5">{toLabel}</label>
          <input type="date" value={toDate} onChange={e => setToDate(e.target.value)} placeholder={placeholder}
            className="w-full text-xs border border-amber-200 rounded-lg px-2 py-1.5 bg-white text-slate-700 focus:outline-none focus:border-amber-400" />
        </div>
      </div>

      <button onClick={handleFind} disabled={!selectedEvent || disabled}
        className="w-full py-2 rounded-xl text-xs font-semibold bg-amber-500 text-white hover:bg-amber-600 transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-sm">
        {findLabel}
      </button>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Main FaqStarter component
// ─────────────────────────────────────────────────────────────────────────────
const FaqStarter: React.FC<FaqStarterProps> = ({ onSelect, disabled, language, relation, profileName }) => {
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [showMuhurta, setShowMuhurta] = useState(false);

  const lang = language in FAQ_CATEGORIES ? language : 'English';

  // Decide whether to use relation-specific or standard categories
  const relKey = (relation || 'Self').trim();
  const relationFaqs = RELATION_FAQS[relKey]?.[lang] ?? RELATION_FAQS[relKey]?.['English'] ?? null;
  const isRelationMode = Boolean(relationFaqs && relationFaqs.length > 0);

  const categories = isRelationMode ? relationFaqs! : (FAQ_CATEGORIES[lang] ?? FAQ_CATEGORIES['English']);
  const activeData = categories.find(c => c.label === activeCategory);

  const muhurtaLabel = language === 'Hindi' ? 'मुहूर्त' : 'Muhurta';
  const relIcon = RELATION_ICONS[relKey] ?? '✨';

  const headerLabel = isRelationMode
    ? `${relIcon} Questions for ${profileName || relKey}`
    : '✨ Popular Questions — Pick a Topic';

  const handleChipClick = (label: string) => {
    if (label === '__muhurta__') {
      setActiveCategory(null);
      setShowMuhurta(prev => !prev);
    } else {
      setShowMuhurta(false);
      setActiveCategory(activeCategory === label ? null : label);
    }
  };

  return (
    <div className="border-t border-slate-100 bg-white px-4 pt-3 pb-1">
      <p className="text-[10px] uppercase tracking-widest text-slate-400 font-semibold mb-2">
        {headerLabel}
      </p>

      {/* Category chips + Muhurta chip */}
      <div className="flex flex-wrap gap-2 mb-2">
        {categories.map(cat => (
          <button
            key={cat.label}
            onClick={() => handleChipClick(cat.label)}
            disabled={disabled}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all
              ${activeCategory === cat.label
                ? 'bg-amber-500 text-white border-amber-500 shadow-sm'
                : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-amber-50 hover:border-amber-300 hover:text-amber-700'
              } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            <span>{cat.emoji}</span>
            <span>{cat.label}</span>
          </button>
        ))}

        {/* Muhurta chip */}
        <button
          onClick={() => handleChipClick('__muhurta__')}
          disabled={disabled}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all
            ${showMuhurta
              ? 'bg-violet-600 text-white border-violet-600 shadow-sm'
              : 'bg-violet-50 text-violet-700 border-violet-200 hover:bg-violet-100 hover:border-violet-400'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          <span>🗓️</span>
          <span>{muhurtaLabel}</span>
        </button>
      </div>

      {/* Muhurta inline panel */}
      {showMuhurta && (
        <MuhurtaPanel
          language={language}
          onSelect={onSelect}
          onClose={() => setShowMuhurta(false)}
          disabled={disabled}
        />
      )}

      {/* Questions for selected FAQ category */}
      {activeData && !showMuhurta && (
        <div className="flex flex-wrap gap-2 mb-2">
          {activeData.questions.map(q => (
            <button
              key={q}
              onClick={() => { onSelect(q); setActiveCategory(null); }}
              disabled={disabled}
              className="px-3 py-1.5 rounded-full text-xs bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-500 hover:text-white hover:border-amber-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default FaqStarter;
