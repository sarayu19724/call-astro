import { useEffect, useState, useCallback } from 'react';
import { ArrowLeft, ChevronLeft, ChevronRight, Sparkles, Loader2, Sunrise, Sunset, MapPin, RefreshCw } from 'lucide-react';

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
interface DayInfo {
  transits: TransitEvent[];
  dasha: DashaEvent[];
  good: MuhurtaWindow[];
  avoid: MuhurtaWindow[];
  muhurta?: MuhurtaDetail | null;
  is_significant: boolean;
  personal_status?: 'favorable' | 'caution' | 'normal';
}
interface MonthData {
  year: number; month: number; swisseph_available: boolean;
  has_dasha_data: boolean; has_chart_data: boolean; has_muhurta_data: boolean;
  location_source?: 'current' | 'birth' | 'unavailable';
  calendar_latitude?: number | null;
  calendar_longitude?: number | null;
  days: Record<string, DayInfo>;
}
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
  has_dasha_data?: boolean;
  muhurta?: MuhurtaDetail | null;
  has_muhurta_data?: boolean;
  location_source?: 'current' | 'birth' | 'unavailable';
  calendar_latitude?: number | null;
  calendar_longitude?: number | null;
  panchang?: {
    tithi: string;
    paksha: string;
    nakshatra: string;
    nakshatra_pada: number;
    yoga: string;
    karana: string;
  } | null;
  personal_status?: 'favorable' | 'caution' | 'normal';
  personal_supportive_reasons?: string[];
  personal_challenging_reasons?: string[];
}
interface MonthSummary {
  transit_count: number;
  dasha_event_count: number;
  significant_day_count: number;
  good_muhurta_days: number;
  avoid_muhurta_days: number;
  favorable_days?: number;
  caution_days?: number;
  has_muhurta_data: boolean;
  most_significant_day: { day: number; topics: string[] } | null;
}

type FilterKey = 'all' | 'favorable' | 'caution' | 'transits' | 'dasha';

const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const WEEKDAY_LABELS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];

const STRINGS: Record<string, {
  title: string; filters: Record<FilterKey, string>; monthAtGlance: string; significantDates: string;
  significantTransits: string; dashaEvents: string; mostSignificant: string;
  viewMonthly: string; whyImportant: string; askAstrologer: string; noData: string; loading: string;
  planetaryEvents: string; yourChart: string; currentDasha: string; significantFor: string;
  swissephMissing: string; noChartYet: string; house: string;
  goodTimes: string; avoidTimes: string; sunrise: string; sunset: string;
  noMuhurtaData: string; goodDaysCount: string; avoidDaysCount: string;
  currentLocation: string; useCurrentLocation: string; locationPermission: string; locationDenied: string;
}> = {
  English: {
    title: 'Astrology Calendar',
    filters: { all: 'All', favorable: 'Favorable', caution: 'Needs Care', transits: 'Transits', dasha: 'Dasha' },
    monthAtGlance: 'Month at a Glance', significantDates: 'potentially significant dates',
    significantTransits: 'planetary movements', dashaEvents: 'Dasha-related events',
    mostSignificant: 'Most significant', viewMonthly: 'View Monthly Analysis',
    whyImportant: 'Why is this important?', askAstrologer: 'Ask Astrologer', noData: 'No events on this day.',
    loading: 'Loading...', planetaryEvents: 'Planetary Events', yourChart: 'Your Chart',
    currentDasha: 'Current Dasha', significantFor: 'Significant For You',
    swissephMissing: 'Transit calculations are not available yet on the server.',
    noChartYet: 'Chat with the astrologer once to unlock personalized relevance.', house: 'House',
    goodTimes: 'Good Times', avoidTimes: 'Avoid These Times', sunrise: 'Sunrise', sunset: 'Sunset',
    noMuhurtaData: 'Timing calculations need your birth location — chat with the astrologer once to unlock them.',
    goodDaysCount: 'days with a favorable Muhurta', avoidDaysCount: 'days with a period to avoid',
    currentLocation: 'Current location', useCurrentLocation: 'Use current location', locationPermission: 'Getting your current location…', locationDenied: 'Using birth location',
  },
  Hindi: {
    title: 'ज्योतिष कैलेंडर',
    filters: { all: 'सभी', favorable: 'अनुकूल', caution: 'सावधानी', transits: 'गोचर', dasha: 'दशा' },
    monthAtGlance: 'माह की झलक', significantDates: 'संभावित महत्वपूर्ण तिथियाँ',
    significantTransits: 'ग्रह गोचर', dashaEvents: 'दशा से जुड़ी घटनाएँ',
    mostSignificant: 'सबसे महत्वपूर्ण', viewMonthly: 'मासिक विश्लेषण देखें',
    whyImportant: 'यह महत्वपूर्ण क्यों है?', askAstrologer: 'ज्योतिषी से पूछें', noData: 'इस दिन कोई घटना नहीं है।',
    loading: 'लोड हो रहा है...', planetaryEvents: 'ग्रह घटनाएँ', yourChart: 'आपकी कुंडली',
    currentDasha: 'वर्तमान दशा', significantFor: 'आपके लिए महत्वपूर्ण',
    swissephMissing: 'गोचर गणना अभी सर्वर पर उपलब्ध नहीं है।',
    noChartYet: 'व्यक्तिगत जानकारी के लिए पहले ज्योतिषी से एक बार बात करें।', house: 'भाव',
    goodTimes: 'शुभ मुहूर्त', avoidTimes: 'इन समयों से बचें', sunrise: 'सूर्योदय', sunset: 'सूर्यास्त',
    noMuhurtaData: 'मुहूर्त गणना के लिए जन्म स्थान चाहिए — पहले ज्योतिषी से एक बार बात करें।',
    goodDaysCount: 'शुभ मुहूर्त वाले दिन', avoidDaysCount: 'बचने योग्य समय वाले दिन',
    currentLocation: 'वर्तमान स्थान', useCurrentLocation: 'वर्तमान स्थान उपयोग करें', locationPermission: 'वर्तमान स्थान प्राप्त किया जा रहा है…', locationDenied: 'जन्म स्थान उपयोग हो रहा है',
  },
  Hinglish: {
    title: 'Astrology Calendar',
    filters: { all: 'All', favorable: 'Favorable', caution: 'Needs Care', transits: 'Transits', dasha: 'Dasha' },
    monthAtGlance: 'Month at a Glance', significantDates: 'potentially significant dates',
    significantTransits: 'planetary movements', dashaEvents: 'Dasha-related events',
    mostSignificant: 'Most significant', viewMonthly: 'View Monthly Analysis',
    whyImportant: 'Yeh important kyun hai?', askAstrologer: 'Astrologer se poochein', noData: 'Is din koi event nahi hai.',
    loading: 'Loading...', planetaryEvents: 'Planetary Events', yourChart: 'Aapki Kundli',
    currentDasha: 'Current Dasha', significantFor: 'Aapke liye significant',
    swissephMissing: 'Transit calculations abhi server par available nahi hain.',
    noChartYet: 'Personalized relevance ke liye pehle ek baar astrologer se baat karein.', house: 'House',
    goodTimes: 'Good Times', avoidTimes: 'Yeh Times Avoid Karein', sunrise: 'Sunrise', sunset: 'Sunset',
    noMuhurtaData: 'Timing calculations ke liye birth location chahiye — pehle astrologer se ek baar baat karein.',
    goodDaysCount: 'din jab favorable Muhurta hai', avoidDaysCount: 'din jab avoid karne wala period hai',
    currentLocation: 'Current location', useCurrentLocation: 'Use current location', locationPermission: 'Current location li ja rahi hai…', locationDenied: 'Birth location use ho rahi hai',
  },
};

function MuhurtaSection({
  title,
  items,
  positive = false,
}: {
  title: string;
  items: MuhurtaWindow[];
  positive?: boolean;
}) {
  if (!items.length) return null;
  const box = positive
    ? 'bg-emerald-50 border-emerald-200'
    : 'bg-rose-50 border-rose-200';
  const titleClass = positive ? 'text-emerald-700' : 'text-rose-600';
  const nameClass = positive ? 'text-emerald-800' : 'text-rose-800';
  const timeClass = positive ? 'text-emerald-700' : 'text-rose-700';
  const noteClass = positive ? 'text-emerald-600' : 'text-rose-600';

  return (
    <div>
      <p className={`text-[10px] uppercase tracking-wide font-semibold mb-1.5 ${titleClass}`}>
        {positive ? '🟢' : '🔴'} {title}
      </p>
      <div className="space-y-1.5">
        {items.map((m, i) => (
          <div key={`${m.name}-${m.start}-${i}`} className={`${box} border rounded-lg px-3 py-2`}>
            <div className="flex items-center justify-between gap-2">
              <span className={`text-xs font-semibold ${nameClass}`}>{m.name}</span>
              <span className={`text-xs ${timeClass}`}>{m.start} – {m.end}</span>
            </div>
            {m.note && <p className={`text-[11px] mt-0.5 ${noteClass}`}>{m.note}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

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

  // Calendar location is separate from birth location.
  // Kundli/Dasha stay based on birth details; sunrise/sunset/Muhurta use
  // the user's current browser location when permission is granted.
  const [currentLocation, setCurrentLocation] = useState<{ latitude: number; longitude: number } | null>(null);
  const [locationStatus, setLocationStatus] = useState<'requesting' | 'ready' | 'denied' | 'unsupported'>('requesting');
  const [locationError, setLocationError] = useState<string | null>(null);

  const requestCurrentLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setLocationStatus('unsupported');
      return;
    }

    setLocationStatus('requesting');
    setLocationError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setCurrentLocation({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
        setLocationStatus('ready');
        setLocationError(null);
      },
      (error) => {
        console.warn('Current location unavailable:', error.message);
        setCurrentLocation(null);
        if (error.code === error.PERMISSION_DENIED) {
          setLocationStatus('denied');
          setLocationError('Location permission was denied. Allow location access for callastro.vercel.app and try again.');
        } else {
          setLocationStatus('unsupported');
          setLocationError(error.message || 'Current location could not be obtained.');
        }
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 5 * 60 * 1000 },
    );
  }, []);

  useEffect(() => {
    requestCurrentLocation();
  }, [requestCurrentLocation]);

  const locationQuery = currentLocation
    ? `?latitude=${encodeURIComponent(currentLocation.latitude)}&longitude=${encodeURIComponent(currentLocation.longitude)}`
    : '';

  const loadMonth = useCallback(async () => {
    setLoading(true);
    try {
      const [monthRes, summaryRes] = await Promise.all([
        fetch(`${API_BASE}/session/${sessionId}/calendar/${year}/${month}${locationQuery}`),
        fetch(`${API_BASE}/session/${sessionId}/calendar/${year}/${month}/summary${locationQuery}`),
      ]);
      if (monthRes.ok) setMonthData(await monthRes.json());
      if (summaryRes.ok) setSummary(await summaryRes.json());
    } catch (err) {
      console.error('Failed to load calendar month:', err);
    } finally {
      setLoading(false);
    }
  }, [sessionId, year, month, locationQuery]);

  useEffect(() => {
    // Wait for the browser location decision first. If permission is denied,
    // locationStatus becomes denied and the calendar intentionally falls back
    // to the birth location.
    if (locationStatus !== 'requesting') loadMonth();
  }, [loadMonth, locationStatus]);

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
      const res = await fetch(`${API_BASE}/session/${sessionId}/calendar/day/${dateStr}${locationQuery}`);
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
      const res = await fetch(`${API_BASE}/session/${sessionId}/calendar/day/${dateStr}?explain=true${currentLocation ? `&latitude=${encodeURIComponent(currentLocation.latitude)}&longitude=${encodeURIComponent(currentLocation.longitude)}` : ''}`);
      if (res.ok) setDayDetail(await res.json());
    } catch (err) {
      console.error('Failed to explain day:', err);
    } finally {
      setExplaining(false);
    }
  };

  const dayMatchesFilter = (info: DayInfo): boolean => {
    switch (filter) {
      case 'favorable': return info.personal_status === 'favorable';
      case 'caution': return info.personal_status === 'caution';
      case 'transits': return info.transits.length > 0;
      case 'dasha': return info.dasha.length > 0;
      default: return true;
    }
  };

  const daysInMonth = new Date(year, month, 0).getDate();
  const firstOfMonth = new Date(year, month - 1, 1);
  const leadingBlanks = (firstOfMonth.getDay() + 6) % 7; // Monday-start offset

  const cells: (number | null)[] = [
    ...Array(leadingBlanks).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

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

          {/* Current calendar location */}
          <div className="bg-white border border-slate-200 rounded-xl px-3 py-2.5 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <MapPin size={15} className="text-amber-500 shrink-0" />
              <div className="min-w-0">
                <p className="text-xs font-semibold text-slate-700">
                  {monthData?.location_source === 'current'
                    ? t.currentLocation
                    : locationStatus === 'requesting'
                      ? t.locationPermission
                      : t.locationDenied}
                </p>
                {currentLocation && (
                  <p className="text-[10px] text-slate-400 truncate">
                    {currentLocation.latitude.toFixed(5)}, {currentLocation.longitude.toFixed(5)}
                  </p>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={requestCurrentLocation}
              disabled={locationStatus === 'requesting'}
              className="shrink-0 flex items-center gap-1.5 text-[11px] font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-lg px-2.5 py-1.5 disabled:opacity-50"
            >
              <RefreshCw size={12} className={locationStatus === 'requesting' ? 'animate-spin' : ''} />
              {t.useCurrentLocation}
            </button>
          </div>
          {locationError && locationStatus !== 'ready' && (
            <div className="text-[11px] text-rose-600 bg-rose-50 border border-rose-100 rounded-lg px-3 py-2">
              {locationError}
            </div>
          )}

          {/* Filters */}
          <div className="flex flex-wrap gap-2">
            {(['all', 'favorable', 'caution', 'transits', 'dasha'] as FilterKey[]).map((key) => (
              <button
                key={key}
                onClick={() => setFilter(key)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition flex items-center gap-1.5 ${
                  filter === key
                    ? key === 'favorable'
                      ? 'bg-emerald-500 text-white border-emerald-500'
                      : key === 'caution'
                        ? 'bg-rose-500 text-white border-rose-500'
                        : key === 'transits'
                          ? 'bg-sky-500 text-white border-sky-500'
                          : key === 'dasha'
                            ? 'bg-violet-500 text-white border-violet-500'
                            : 'bg-amber-500 text-white border-amber-500'
                    : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                }`}
              >
                {key !== 'all' && (
                  <span className={`w-1.5 h-1.5 rounded-full ${
                    key === 'favorable' ? 'bg-emerald-500' :
                    key === 'caution' ? 'bg-rose-500' :
                    key === 'transits' ? 'bg-sky-500' : 'bg-violet-500'
                  }`} />
                )}
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
                  const hasFavorable = info?.personal_status === 'favorable';
                  const hasCaution = info?.personal_status === 'caution';
                  const hasTransit = !!info?.transits?.length;
                  const hasDasha = !!info?.dasha?.length;
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
                        {hasFavorable && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-emerald-500'}`} />}
                        {hasCaution && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-rose-500'}`} />}
                        {hasTransit && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-sky-500'}`} />}
                        {hasDasha && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-violet-500'}`} />}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}

            {!loading && monthData && (
              <div className="flex flex-wrap gap-3 mt-4 pt-3 border-t border-slate-100 text-[10px] text-slate-400">
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> {t.filters.favorable}</span>
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-rose-500" /> {t.filters.caution}</span>
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-sky-500" /> {t.significantTransits}</span>
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-violet-500" /> {t.dashaEvents}</span>
              </div>
            )}
          </div>

          {/* Day detail panel */}
          {selectedDay && (
            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
              <h3 className="text-sm font-bold text-slate-800 mb-1">
                {MONTH_NAMES[month - 1]} {selectedDay}, {year}
              </h3>
              <p className="text-[10px] text-slate-400 mb-3">
                <MapPin size={10} className="inline mr-1" />
                {dayDetail?.location_source === 'current' ? t.currentLocation : t.locationDenied}
              </p>

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

                  {dayDetail.muhurta && dayDetail.muhurta.abhijit.length > 0 && (
                    <MuhurtaSection title="Favorable Muhurta" items={[
                      ...dayDetail.muhurta.abhijit,
                      ...dayDetail.muhurta.brahma,
                    ]} positive />
                  )}

                  {dayDetail.muhurta && (
                    <MuhurtaSection title={t.avoidTimes} items={[
                      ...dayDetail.muhurta.rahu_kalam,
                      ...dayDetail.muhurta.yamaganda,
                      ...dayDetail.muhurta.gulika_kalam,
                      ...dayDetail.muhurta.durmuhurtham,
                    ]} />
                  )}

                  {dayDetail.panchang && (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl px-3 py-3">
                      <p className="text-[10px] uppercase tracking-wide text-amber-700 font-semibold mb-2">
                        Panchang
                      </p>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs text-slate-700">
                        <div><span className="text-slate-400">Tithi:</span> {dayDetail.panchang.tithi}</div>
                        <div><span className="text-slate-400">Paksha:</span> {dayDetail.panchang.paksha}</div>
                        <div><span className="text-slate-400">Nakshatra:</span> {dayDetail.panchang.nakshatra} (Pada {dayDetail.panchang.nakshatra_pada})</div>
                        <div><span className="text-slate-400">Yoga:</span> {dayDetail.panchang.yoga}</div>
                        <div><span className="text-slate-400">Karana:</span> {dayDetail.panchang.karana}</div>
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

                  {dayDetail.personal_status && (
                    <div className={`rounded-xl px-3 py-2 border ${
                      dayDetail.personal_status === 'favorable'
                        ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                        : dayDetail.personal_status === 'caution'
                          ? 'bg-rose-50 border-rose-200 text-rose-700'
                          : 'bg-slate-50 border-slate-200 text-slate-600'
                    }`}>
                      <p className="text-[10px] uppercase tracking-wide font-semibold mb-1">
                        {t.significantFor}
                      </p>
                      <p className="text-xs font-medium capitalize">
                        {dayDetail.personal_status}
                      </p>
                      {dayDetail.personal_supportive_reasons?.length ? (
                        <p className="text-[11px] mt-1">{dayDetail.personal_supportive_reasons.join(' • ')}</p>
                      ) : null}
                      {dayDetail.personal_challenging_reasons?.length ? (
                        <p className="text-[11px] mt-1">{dayDetail.personal_challenging_reasons.join(' • ')}</p>
                      ) : null}
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

                  {(!dayDetail.planetary_positions || dayDetail.planetary_positions.length === 0) &&
                    !dayDetail.current_mahadasha &&
                    !dayDetail.panchang &&
                    !(dayDetail.muhurta && (
                      dayDetail.muhurta.abhijit.length ||
                      dayDetail.muhurta.brahma.length ||
                      dayDetail.muhurta.rahu_kalam.length ||
                      dayDetail.muhurta.yamaganda.length ||
                      dayDetail.muhurta.gulika_kalam.length ||
                      dayDetail.muhurta.durmuhurtham.length
                    )) && (
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
                {summary.has_muhurta_data && (
                  <>
                    <li>• {summary.good_muhurta_days} {t.goodDaysCount}</li>
                    <li>• {summary.avoid_muhurta_days} {t.avoidDaysCount}</li>
                  </>
                )}
                {typeof summary.favorable_days === 'number' && (
                  <li>• {summary.favorable_days} favorable personal days</li>
                )}
                {typeof summary.caution_days === 'number' && (
                  <li>• {summary.caution_days} personal caution days</li>
                )}
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