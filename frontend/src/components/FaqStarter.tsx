import React, { useState } from 'react';

interface FaqStarterProps {
  onSelect: (question: string) => void;
  disabled: boolean;
  language: string;
}

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

const MuhurtaPanel: React.FC<{ language: string; onSelect: (q: string) => void; onClose: () => void; disabled: boolean }> = ({ language, onSelect, onClose, disabled }) => {
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
  const findLabel = language === 'Hindi' ? '🔍 मुहूर्त खोजें' : language === 'Hinglish' ? '🔍 Muhurta Dhundho' : '🔍 Find Muhurta';
  const fromLabel = language === 'Hindi' ? 'इस तारीख से' : language === 'Hinglish' ? 'Is date ke baad' : 'From date (optional)';
  const toLabel = language === 'Hindi' ? 'इस तारीख तक' : language === 'Hinglish' ? 'Is date tak' : 'To date (optional)';
  const eventLabel = language === 'Hindi' ? 'कार्यक्रम चुनें:' : language === 'Hinglish' ? 'Event chunein:' : 'Select event:';

  return (
    <div className="mt-2 mb-2 p-3 rounded-2xl border border-amber-200 bg-amber-50 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between mb-2.5">
        <span className="text-xs font-semibold text-amber-800 flex items-center gap-1.5">
          🗓️ {language === 'Hindi' ? 'मुहूर्त खोजक' : language === 'Hinglish' ? 'Muhurta Finder' : 'Muhurta Finder'}
        </span>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xs leading-none">✕</button>
      </div>

      {/* Event selector */}
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

      {/* Date range */}
      <div className="flex gap-2 mb-3">
        <div className="flex-1">
          <label className="text-[10px] text-amber-700 font-medium block mb-0.5">{fromLabel}</label>
          <input
            type="date"
            value={fromDate}
            onChange={e => setFromDate(e.target.value)}
            placeholder={placeholder}
            className="w-full text-xs border border-amber-200 rounded-lg px-2 py-1.5 bg-white text-slate-700 focus:outline-none focus:border-amber-400"
          />
        </div>
        <div className="flex-1">
          <label className="text-[10px] text-amber-700 font-medium block mb-0.5">{toLabel}</label>
          <input
            type="date"
            value={toDate}
            onChange={e => setToDate(e.target.value)}
            placeholder={placeholder}
            className="w-full text-xs border border-amber-200 rounded-lg px-2 py-1.5 bg-white text-slate-700 focus:outline-none focus:border-amber-400"
          />
        </div>
      </div>

      {/* Find button */}
      <button
        onClick={handleFind}
        disabled={!selectedEvent || disabled}
        className="w-full py-2 rounded-xl text-xs font-semibold bg-amber-500 text-white hover:bg-amber-600 transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-sm"
      >
        {findLabel}
      </button>
    </div>
  );
};

const FaqStarter: React.FC<FaqStarterProps> = ({ onSelect, disabled, language }) => {
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [showMuhurta, setShowMuhurta] = useState(false);
  const lang = language in FAQ_CATEGORIES ? language : 'Hinglish';
  const categories = FAQ_CATEGORIES[lang];
  const activeData = categories.find(c => c.label === activeCategory);

  const muhurtaLabel = language === 'Hindi' ? 'मुहूर्त' : 'Muhurta';

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
        ✨ Popular Questions — Pick a Topic
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

        {/* Muhurta chip — styled differently to stand out */}
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
