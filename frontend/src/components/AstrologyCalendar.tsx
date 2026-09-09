import { useEffect, useState, useCallback } from 'react';
import { ArrowLeft, ChevronLeft, ChevronRight, Sparkles, Loader2, Sunrise, Sunset } from 'lucide-react';

const API_BASE = ((import.meta as ImportMeta & { env?: { VITE_API_BASE?: string } }).env?.VITE_API_BASE) || '/api';

interface AstrologyCalendarProps {
  sessionId: string;
  language: string;
  onBack: () => void;
}

interface Relevance { house: number | null; topics: string[]; }
interface TransitEvent { planet: string; new_sign: string; relevance?: Relevance; }
interface DashaEvent { date: string; mahadasha: string; antardasha: string; boundary: string; }
interface MuhurtaWindow { name: string; start: string; end: string; note: string; }

interface MuhurtaDetail {
  sunrise: string;
  sunset: string;
  abhijit: MuhurtaWindow[];
  brahma: MuhurtaWindow[];
  rahu_kalam: MuhurtaWindow[];
  yamaganda: MuhurtaWindow[];
  gulika_kalam: MuhurtaWindow[];
  durmuhurtham: MuhurtaWindow[];
}

interface PanchangDetail {
  tithi: string;
  paksha: string;
  nakshatra: string;
  nakshatra_pada: number;
  yoga: string;
  karana: string;
}

interface DayInfo {
  transits: TransitEvent[];
  dasha: DashaEvent[];
  muhurta?: MuhurtaDetail | null;
  is_significant: boolean;
  personal_status: 'favorable' | 'caution' | 'normal';
  personal_score: number;
}

interface MonthData {
  year: number; month: number; swisseph_available: boolean;
  has_dasha_data: boolean; has_chart_data: boolean; has_muhurta_data: boolean;
  days: Record<string, DayInfo>;
}

interface DayDetail {
  available: boolean;
  date?: string;
  planetary_positions?: { planet: string; sign: string; relevance?: Relevance }[];
  current_mahadasha?: string | null;
  current_antardasha?: string | null;
  significant_topics?: string[];
  is_auspicious_heuristic?: boolean;
  explanation?: string;
  swisseph_available?: boolean;
  muhurta?: MuhurtaDetail | null;
  has_muhurta_data?: boolean;
  panchang?: PanchangDetail | null;
  personal_status?: 'favorable' | 'caution' | 'normal';
  personal_score?: number;
  personal_supportive_reasons?: string[];
  personal_challenging_reasons?: string[];
}

interface MonthSummary {
  transit_count: number;
  dasha_event_count: number;
  significant_day_count: number;
  favorable_days: number;
  caution_days: number;
  has_muhurta_data: boolean;
  most_significant_day: { day: number; topics: string[] } | null;
}

type FilterKey = 'all' | 'transits' | 'dasha' | 'important';

const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const WEEKDAY_LABELS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];

const STRINGS: Record<string, {
  title: string; filters: Record<FilterKey, string>; monthAtGlance: string; significantDates: string;
  significantTransits: string; dashaEvents: string; mostSignificant: string;
  viewMonthly: string; whyImportant: string; askAstrologer: string; noData: string; loading: string;
  planetaryEvents: string; yourChart: string; currentDasha: string; significantFor: string;
  swissephMissing: string; noChartYet: string; house: string;
  favorableMuhurta: string; periodsToAvoid: string; sunrise: string; sunset: string;
  noMuhurtaData: string; favorableDaysCount: string; cautionDaysCount: string;
  favorableForYou: string; cautionForYou: string;
  personalLabel: string; statusFavorable: string; statusCaution: string; statusNormal: string;
  supportiveLabel: string; challengingLabel: string; panchangLabel: string;
  tithiLabel: string; nakshatraLabel: string; yogaLabel: string; karanaLabel: string;
}> = {
  English: {
    title: 'Astrology Calendar',
    filters: { all: 'All', transits: 'Transits', dasha: 'Dasha', important: 'For Me' },
    monthAtGlance: 'Month at a Glance', significantDates: 'potentially significant dates',
    significantTransits: 'planetary movements', dashaEvents: 'Dasha-related events',
    mostSignificant: 'Most significant', viewMonthly: 'View Monthly Analysis',
    whyImportant: 'Why is this important?', askAstrologer: 'Ask Astrologer', noData: 'No events on this day.',
    loading: 'Loading...', planetaryEvents: 'Planetary Events', yourChart: 'Your Chart',
    currentDasha: 'Current Dasha', significantFor: 'Significant For You',
    swissephMissing: 'Transit calculations are not available yet on the server.',
    noChartYet: 'Chat with the astrologer once to unlock personalized relevance.', house: 'House',
    favorableMuhurta: 'Favorable Muhurta', periodsToAvoid: 'Periods to Avoid',
    sunrise: 'Sunrise', sunset: 'Sunset',
    noMuhurtaData: 'Timing calculations need your birth location — chat with the astrologer once to unlock them.',
    favorableDaysCount: 'favorable days for you', cautionDaysCount: 'days needing extra caution',
    favorableForYou: 'Favorable for you', cautionForYou: 'Caution for you',
    personalLabel: 'Personal', statusFavorable: 'Favorable', statusCaution: 'Caution', statusNormal: 'Normal',
    supportiveLabel: 'Supportive factors', challengingLabel: 'Challenging factors', panchangLabel: 'Panchang',
    tithiLabel: 'Tithi', nakshatraLabel: 'Nakshatra', yogaLabel: 'Yoga', karanaLabel: 'Karana',
  },
  Hindi: {
    title: 'ज्योतिष कैलेंडर',
    filters: { all: 'सभी', transits: 'गोचर', dasha: 'दशा', important: 'मेरे लिए' },
    monthAtGlance: 'माह की झलक', significantDates: 'संभावित महत्वपूर्ण तिथियाँ',
    significantTransits: 'ग्रह गोचर', dashaEvents: 'दशा से जुड़ी घटनाएँ',
    mostSignificant: 'सबसे महत्वपूर्ण', viewMonthly: 'मासिक विश्लेषण देखें',
    whyImportant: 'यह महत्वपूर्ण क्यों है?', askAstrologer: 'ज्योतिषी से पूछें', noData: 'इस दिन कोई घटना नहीं है।',
    loading: 'लोड हो रहा है...', planetaryEvents: 'ग्रह घटनाएँ', yourChart: 'आपकी कुंडली',
    currentDasha: 'वर्तमान दशा', significantFor: 'आपके लिए महत्वपूर्ण',
    swissephMissing: 'गोचर गणना अभी सर्वर पर उपलब्ध नहीं है।',
    noChartYet: 'व्यक्तिगत जानकारी के लिए पहले ज्योतिषी से एक बार बात करें।', house: 'भाव',
    favorableMuhurta: 'शुभ मुहूर्त', periodsToAvoid: 'बचने योग्य समय',
    sunrise: 'सूर्योदय', sunset: 'सूर्यास्त',
    noMuhurtaData: 'मुहूर्त गणना के लिए जन्म स्थान चाहिए — पहले ज्योतिषी से एक बार बात करें।',
    favorableDaysCount: 'आपके लिए शुभ दिन', cautionDaysCount: 'सावधानी वाले दिन',
    favorableForYou: 'आपके लिए शुभ', cautionForYou: 'सावधानी',
    personalLabel: 'व्यक्तिगत', statusFavorable: 'शुभ', statusCaution: 'सावधानी', statusNormal: 'सामान्य',
    supportiveLabel: 'सहायक कारक', challengingLabel: 'चुनौतीपूर्ण कारक', panchangLabel: 'पंचांग',
    tithiLabel: 'तिथि', nakshatraLabel: 'नक्षत्र', yogaLabel: 'योग', karanaLabel: 'करण',
  },
  Hinglish: {
    title: 'Astrology Calendar',
    filters: { all: 'All', transits: 'Transits', dasha: 'Dasha', important: 'For Me' },
    monthAtGlance: 'Month at a Glance', significantDates: 'potentially significant dates',
    significantTransits: 'planetary movements', dashaEvents: 'Dasha-related events',
    mostSignificant: 'Most significant', viewMonthly: 'View Monthly Analysis',
    whyImportant: 'Yeh important kyun hai?', askAstrologer: 'Astrologer se poochein', noData: 'Is din koi event nahi hai.',
    loading: 'Loading...', planetaryEvents: 'Planetary Events', yourChart: 'Aapki Kundli',
    currentDasha: 'Current Dasha', significantFor: 'Aapke liye significant',
    swissephMissing: 'Transit calculations abhi server par available nahi hain.',
    noChartYet: 'Personalized relevance ke liye pehle ek baar astrologer se baat karein.', house: 'House',
    favorableMuhurta: 'Favorable Muhurta', periodsToAvoid: 'Periods to Avoid',
    sunrise: 'Sunrise', sunset: 'Sunset',
    noMuhurtaData: 'Timing calculations ke liye birth location chahiye — pehle astrologer se ek baar baat karein.',
    favorableDaysCount: 'din jo aapke liye favorable hain', cautionDaysCount: 'din jinme thoda caution rakhna hai',
    favorableForYou: 'Aapke liye favorable', cautionForYou: 'Caution',
    personalLabel: 'Personal', statusFavorable: 'Favorable', statusCaution: 'Caution', statusNormal: 'Normal',
    supportiveLabel: 'Supportive factors', challengingLabel: 'Challenging factors', panchangLabel: 'Panchang',
    tithiLabel: 'Tithi', nakshatraLabel: 'Nakshatra', yogaLabel: 'Yoga', karanaLabel: 'Karana',
  },
};

export default function AstrologyCalendar({ sessionId, language, onBack }: AstrologyCalendarProps) {
  const t = STRINGS[language] || STRINGS.Hinglish;
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1); // 1-12
  const [monthData, setMonthData] = useState<MonthData | null>(null);
  const [summary, setSummary] = useState<MonthSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterKey>('all');

  const [selectedDay, setSelectedDay] = useState<number | null>(null);
  const [dayDetail, setDayDetail] = useState<DayDetail | null>(null);
  const [dayLoading, setDayLoading] = useState(false);
  const [explaining, setExplaining] = useState(false);

  const loadMonth = useCallback(async () => {
    setLoading(true);
    try {
      const [monthRes, summaryRes] = await Promise.all([
        fetch(`${API_BASE}/session/${sessionId}/calendar/${year}/${month}`),
        fetch(`${API_BASE}/session/${sessionId}/calendar/${year}/${month}/summary`),
      ]);
      if (monthRes.ok) setMonthData(await monthRes.json());
      if (summaryRes.ok) setSummary(await summaryRes.json());
    } catch (err) {
      console.error('Failed to load calendar month:', err);
    } finally {
      setLoading(false);
    }
  }, [sessionId, year, month]);

  useEffect(() => { loadMonth(); }, [loadMonth]);

  const changeMonth = (delta: number) => {
    setSelectedDay(null);
    setDayDetail(null);
    let newMonth = month + delta;
    let newYear = year;
    if (newMonth < 1) { newMonth = 12; newYear -= 1; }
    if (newMonth > 12) { newMonth = 1; newYear += 1; }
    setMonth(newMonth);
    setYear(newYear);
  };

  const openDay = async (day: number) => {
    setSelectedDay(day);
    setDayDetail(null);
    setDayLoading(true);
    try {
      const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const res = await fetch(`${API_BASE}/session/${sessionId}/calendar/day/${dateStr}`);
      if (res.ok) setDayDetail(await res.json());
    } catch (err) {
      console.error('Failed to load day detail:', err);
    } finally {
      setDayLoading(false);
    }
  };

  const explainDay = async () => {
    if (!selectedDay) return;
    setExplaining(true);
    try {
      const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(selectedDay).padStart(2, '0')}`;
      const res = await fetch(`${API_BASE}/session/${sessionId}/calendar/day/${dateStr}?explain=true`);
      if (res.ok) setDayDetail(await res.json());
    } catch (err) {
      console.error('Failed to explain day:', err);
    } finally {
      setExplaining(false);
    }
  };

  const dayMatchesFilter = (info: DayInfo): boolean => {
    switch (filter) {
      case 'transits':
        return info.transits.length > 0;
      case 'dasha':
        return info.dasha.length > 0;
      case 'important':
        return info.personal_status !== 'normal' || info.is_significant;
      default:
        return true;
    }
  };

  // Renders one Muhurta window group (e.g. Abhijit, Rahu Kalam). Returns
  // null when there's nothing to show, so callers can drop it straight
  // into JSX without an extra guard.
  const renderMuhurtaGroup = (title: string, windows: MuhurtaWindow[] | undefined, type: 'good' | 'avoid') => {
    if (!windows || windows.length === 0) return null;
    const good = type === 'good';

    return (
      <div key={title}>
        <p className={`text-[10px] uppercase tracking-wide font-semibold mb-1.5 ${good ? 'text-emerald-600' : 'text-rose-600'}`}>
          {title}
        </p>
        <div className="space-y-1.5">
          {windows.map((m) => (
            <div
              key={`${m.name}-${m.start}`}
              className={`rounded-lg px-3 py-2 border ${good ? 'bg-emerald-50 border-emerald-200' : 'bg-rose-50 border-rose-200'}`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-800">{m.name}</span>
                <span className="text-xs text-slate-600">{m.start} – {m.end}</span>
              </div>
              {m.note && <p className="text-[11px] text-slate-500 mt-0.5">{m.note}</p>}
            </div>
          ))}
        </div>
      </div>
    );
  };

  const daysInMonth = new Date(year, month, 0).getDate();
  const firstOfMonth = new Date(year, month - 1, 1);
  const leadingBlanks = (firstOfMonth.getDay() + 6) % 7; // Monday-start offset

  const cells: (number | null)[] = [
    ...Array(leadingBlanks).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  const hasAnyMuhurtaWindows = (m?: MuhurtaDetail | null): boolean => {
    if (!m) return false;
    return (
      m.abhijit.length > 0 || m.brahma.length > 0 ||
      m.rahu_kalam.length > 0 || m.yamaganda.length > 0 ||
      m.gulika_kalam.length > 0 || m.durmuhurtham.length > 0
    );
  };

  const personalStatusLabel = (status?: 'favorable' | 'caution' | 'normal') => {
    if (status === 'favorable') return t.statusFavorable;
    if (status === 'caution') return t.statusCaution;
    return t.statusNormal;
  };

  return (
    <div className="flex flex-col h-full bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between shrink-0">
        <button onClick={onBack} className="flex items-center gap-1.5 text-slate-500 hover:text-slate-800 text-sm font-medium transition">
          <ArrowLeft size={16} /> Dashboard
        </button>
        <h1 className="text-lg font-bold text-slate-800 flex items-center gap-2">
          <Sparkles size={18} className="text-amber-500" /> {t.title}
        </h1>
        <div className="w-24" />
      </header>

      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        <div className="max-w-3xl mx-auto space-y-5">

          {!loading && monthData && !monthData.swisseph_available && (
            <div className="bg-amber-50 border border-amber-200 text-amber-700 text-xs rounded-xl px-4 py-2.5">
              {t.swissephMissing}
            </div>
          )}
          {!loading && monthData && !monthData.has_chart_data && (
            <div className="bg-slate-100 border border-slate-200 text-slate-500 text-xs rounded-xl px-4 py-2.5">
              {t.noChartYet}
            </div>
          )}
          {!loading && monthData && monthData.has_chart_data && !monthData.has_muhurta_data && (
            <div className="bg-slate-100 border border-slate-200 text-slate-500 text-xs rounded-xl px-4 py-2.5">
              {t.noMuhurtaData}
            </div>
          )}

          {/* Filters */}
          <div className="flex flex-wrap gap-2">
            {(Object.keys(t.filters) as FilterKey[]).map((key) => (
              <button
                key={key}
                onClick={() => setFilter(key)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition ${
                  filter === key
                    ? 'bg-amber-500 text-white border-amber-500'
                    : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                }`}
              >
                {t.filters[key]}
              </button>
            ))}
          </div>

          {/* Month navigation + grid */}
          <div className="bg-white border border-slate-200 rounded-2xl p-4 md:p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <button onClick={() => changeMonth(-1)} className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-50 rounded-lg transition">
                <ChevronLeft size={18} />
              </button>
              <span className="font-semibold text-slate-800 text-sm">{MONTH_NAMES[month - 1]} {year}</span>
              <button onClick={() => changeMonth(1)} className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-50 rounded-lg transition">
                <ChevronRight size={18} />
              </button>
            </div>

            <div className="grid grid-cols-7 gap-1 text-center text-[10px] font-semibold text-slate-400 mb-1">
              {WEEKDAY_LABELS.map((d) => <div key={d}>{d}</div>)}
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-16 text-slate-400 gap-2">
                <Loader2 size={16} className="animate-spin" /> {t.loading}
              </div>
            ) : (
              <div className="grid grid-cols-7 gap-1">
                {cells.map((day, idx) => {
                  if (day === null) return <div key={`b-${idx}`} />;
                  const info = monthData?.days[String(day)];
                  const visible = info ? dayMatchesFilter(info) : false;
                  const hasTransit = !!info?.transits.length;
                  const hasDasha = !!info?.dasha.length;
                  const isFavorable = info?.personal_status === 'favorable';
                  const isCaution = info?.personal_status === 'caution';
                  const isToday = year === today.getFullYear() && month === today.getMonth() + 1 && day === today.getDate();
                  return (
                    <button
                      key={day}
                      onClick={() => openDay(day)}
                      className={`aspect-square rounded-lg flex flex-col items-center justify-center text-xs relative transition
                        ${selectedDay === day ? 'bg-amber-500 text-white' : isToday ? 'bg-amber-50 text-amber-700 font-semibold' : 'hover:bg-slate-50 text-slate-700'}
                        ${!visible && filter !== 'all' ? 'opacity-30' : ''}`}
                    >
                      <span>{day}</span>
                      <span className="flex gap-0.5 mt-0.5">
                        {isFavorable && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-emerald-500'}`} />}
                        {isCaution && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-rose-500'}`} />}
                        {hasTransit && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-sky-500'}`} />}
                        {hasDasha && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-violet-500'}`} />}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}

            <div className="flex flex-wrap gap-3 mt-4 pt-3 border-t border-slate-100 text-[10px] text-slate-400">
              <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> {t.favorableForYou}</span>
              <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-rose-500" /> {t.cautionForYou}</span>
              <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-sky-500" /> {t.significantTransits}</span>
              <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-violet-500" /> {t.dashaEvents}</span>
            </div>
          </div>

          {/* Day detail panel */}
          {selectedDay && (
            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
              <h3 className="text-sm font-bold text-slate-800 mb-3">
                {MONTH_NAMES[month - 1]} {selectedDay}, {year}
              </h3>

              {dayLoading ? (
                <div className="flex items-center gap-2 text-slate-400 text-sm py-4">
                  <Loader2 size={14} className="animate-spin" /> {t.loading}
                </div>
              ) : dayDetail && dayDetail.available ? (
                <div className="space-y-4">
                  {dayDetail.muhurta && (
                    <div className="flex items-center gap-4 text-xs text-slate-500 bg-slate-50 rounded-xl px-3 py-2">
                      <span className="flex items-center gap-1"><Sunrise size={12} className="text-amber-500" /> {t.sunrise}: {dayDetail.muhurta.sunrise}</span>
                      <span className="flex items-center gap-1"><Sunset size={12} className="text-amber-600" /> {t.sunset}: {dayDetail.muhurta.sunset}</span>
                    </div>
                  )}

                  {dayDetail.panchang && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-2">{t.panchangLabel}</p>
                      <div className="grid grid-cols-2 gap-2 text-xs bg-slate-50 rounded-xl p-3">
                        <div>
                          <span className="text-slate-400">{t.tithiLabel}</span>
                          <p className="font-semibold text-slate-700">
                            {dayDetail.panchang.paksha} {dayDetail.panchang.tithi}
                          </p>
                        </div>
                        <div>
                          <span className="text-slate-400">{t.nakshatraLabel}</span>
                          <p className="font-semibold text-slate-700">
                            {dayDetail.panchang.nakshatra}
                            {' '}— Pada {dayDetail.panchang.nakshatra_pada}
                          </p>
                        </div>
                        <div>
                          <span className="text-slate-400">{t.yogaLabel}</span>
                          <p className="font-semibold text-slate-700">{dayDetail.panchang.yoga}</p>
                        </div>
                        <div>
                          <span className="text-slate-400">{t.karanaLabel}</span>
                          <p className="font-semibold text-slate-700">{dayDetail.panchang.karana}</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {dayDetail.muhurta && hasAnyMuhurtaWindows(dayDetail.muhurta) && (
                    <div className="space-y-4">
                      <div>
                        <p className="text-[10px] uppercase tracking-wide text-emerald-600 font-semibold mb-2">
                          {t.favorableMuhurta}
                        </p>
                        <div className="space-y-3">
                          {renderMuhurtaGroup('Abhijit Muhurta', dayDetail.muhurta.abhijit, 'good')}
                          {renderMuhurtaGroup('Brahma Muhurta', dayDetail.muhurta.brahma, 'good')}
                        </div>
                      </div>

                      <div>
                        <p className="text-[10px] uppercase tracking-wide text-rose-600 font-semibold mb-2">
                          {t.periodsToAvoid}
                        </p>
                        <div className="space-y-3">
                          {renderMuhurtaGroup('Rahu Kalam', dayDetail.muhurta.rahu_kalam, 'avoid')}
                          {renderMuhurtaGroup('Yamaganda', dayDetail.muhurta.yamaganda, 'avoid')}
                          {renderMuhurtaGroup('Gulika Kalam', dayDetail.muhurta.gulika_kalam, 'avoid')}
                          {renderMuhurtaGroup('Durmuhurtham', dayDetail.muhurta.durmuhurtham, 'avoid')}
                        </div>
                      </div>
                    </div>
                  )}

                  {dayDetail.planetary_positions && dayDetail.planetary_positions.length > 0 && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1.5">{t.planetaryEvents}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {dayDetail.planetary_positions.map((p) => (
                          <span key={p.planet} className="text-xs bg-sky-50 text-sky-700 border border-sky-200 rounded-full px-2.5 py-1">
                            {p.planet} → {p.sign}{p.relevance?.house ? ` (${t.house} ${p.relevance.house})` : ''}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {dayDetail.current_mahadasha && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1.5">{t.currentDasha}</p>
                      <span className="text-xs bg-violet-50 text-violet-700 border border-violet-200 rounded-full px-2.5 py-1">
                        {dayDetail.current_mahadasha}{dayDetail.current_antardasha ? ` / ${dayDetail.current_antardasha}` : ''}
                      </span>
                    </div>
                  )}

                  {dayDetail.significant_topics && dayDetail.significant_topics.length > 0 && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1.5">{t.significantFor}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {dayDetail.significant_topics.map((topic) => (
                          <span key={topic} className="text-xs bg-amber-50 text-amber-700 border border-amber-200 rounded-full px-2.5 py-1 capitalize">
                            ⭐ {topic}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {dayDetail.personal_status && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1.5">{t.personalLabel}</p>
                      <div
                        className={`rounded-lg px-3 py-2 border text-xs ${
                          dayDetail.personal_status === 'favorable'
                            ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                            : dayDetail.personal_status === 'caution'
                            ? 'bg-rose-50 border-rose-200 text-rose-700'
                            : 'bg-slate-50 border-slate-200 text-slate-600'
                        }`}
                      >
                        <span className="font-semibold">{personalStatusLabel(dayDetail.personal_status)}</span>
                        {typeof dayDetail.personal_score === 'number' && (
                          <span className="ml-2 text-slate-400">({dayDetail.personal_score})</span>
                        )}
                      </div>

                      {dayDetail.personal_supportive_reasons && dayDetail.personal_supportive_reasons.length > 0 && (
                        <div className="mt-2">
                          <p className="text-[10px] text-emerald-600 font-medium mb-1">{t.supportiveLabel}</p>
                          <ul className="text-xs text-slate-600 space-y-0.5 list-disc list-inside">
                            {dayDetail.personal_supportive_reasons.map((r, i) => <li key={i}>{r}</li>)}
                          </ul>
                        </div>
                      )}

                      {dayDetail.personal_challenging_reasons && dayDetail.personal_challenging_reasons.length > 0 && (
                        <div className="mt-2">
                          <p className="text-[10px] text-rose-600 font-medium mb-1">{t.challengingLabel}</p>
                          <ul className="text-xs text-slate-600 space-y-0.5 list-disc list-inside">
                            {dayDetail.personal_challenging_reasons.map((r, i) => <li key={i}>{r}</li>)}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}

                  {(!dayDetail.planetary_positions || dayDetail.planetary_positions.length === 0) &&
                    !dayDetail.current_mahadasha &&
                    !dayDetail.muhurta &&
                    !dayDetail.panchang && (
                      <p className="text-xs text-slate-400 italic">{t.noData}</p>
                  )}

                  {dayDetail.explanation && (
                    <p className="text-sm text-slate-700 leading-relaxed border-t border-slate-100 pt-3">
                      {dayDetail.explanation}
                    </p>
                  )}

                  <button
                    onClick={explainDay}
                    disabled={explaining}
                    className="text-xs font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-lg px-3 py-1.5 transition disabled:opacity-50"
                  >
                    {explaining ? t.loading : t.whyImportant}
                  </button>
                </div>
              ) : (
                <p className="text-xs text-slate-400 italic">{t.noData}</p>
              )}
            </div>
          )}

          {/* Month at a glance */}
          {!loading && summary && (
            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
              <h3 className="text-sm font-bold text-slate-800 mb-3">{t.monthAtGlance.toUpperCase()} — {MONTH_NAMES[month - 1]} {year}</h3>
              <ul className="text-sm text-slate-700 space-y-1.5">
                <li>• {summary.favorable_days} {t.favorableDaysCount}</li>
                <li>• {summary.caution_days} {t.cautionDaysCount}</li>
                <li>• {summary.transit_count} {t.significantTransits}</li>
                <li>• {summary.dasha_event_count} {t.dashaEvents}</li>
                <li>• {summary.significant_day_count} {t.significantDates}</li>
              </ul>
              {summary.most_significant_day && (
                <div className="mt-3 pt-3 border-t border-slate-100">
                  <p className="text-xs text-slate-400 font-medium mb-1">{t.mostSignificant}</p>
                  <button
                    onClick={() => openDay(summary.most_significant_day!.day)}
                    className="text-sm font-semibold text-amber-700 hover:underline"
                  >
                    ⭐ {MONTH_NAMES[month - 1]} {summary.most_significant_day.day} — {summary.most_significant_day.topics.join(', ')}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}