import { useEffect, useState, useCallback, useRef } from 'react';
import { ArrowLeft, ChevronLeft, ChevronRight, Sparkles, Loader2, Sunrise, Sunset, MapPin, RefreshCw, Navigation, Search } from 'lucide-react';

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
  personal_status?: 'favorable' | 'normal';
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
  personal_status?: 'favorable' | 'normal';
  personal_supportive_reasons?: string[];
}
interface MonthSummary {
  transit_count: number;
  dasha_event_count: number;
  significant_day_count: number;
  favorable_days: number;
  favorable_dates?: number[];
  has_muhurta_data: boolean;
  most_significant_day: { day: number; topics: string[] } | null;
}

type FilterKey =
  | 'all'
  | 'transits'
  | 'dasha'
  | 'important'
  | 'career'
  | 'finance'
  | 'marriage'
  | 'health'
  | 'education';
type LocationMode = 'geolocation' | 'manual';
type LocationStatus = 'requesting' | 'ready' | 'denied' | 'unsupported' | 'manual_pending' | 'manual_error';

const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const WEEKDAY_LABELS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];

const HOUSE_TOPIC_FILTERS: Record<Exclude<FilterKey, 'all' | 'transits' | 'dasha' | 'important'>, string[]> = {
  career: ['career', 'profession', 'work', 'job'],
  finance: ['finance', 'finances', 'financial', 'wealth', 'money', 'income', 'gains'],
  marriage: ['marriage', 'spouse', 'partnership', 'relationship', 'relationships'],
  health: ['health', 'illness', 'disease', 'wellness'],
  education: ['education', 'learning', 'study', 'studies', 'academic'],
};

const STRINGS: Record<string, {
  title: string; filters: Record<FilterKey, string>; monthAtGlance: string; significantDates: string;
  significantTransits: string; dashaEvents: string; mostSignificant: string;
  viewMonthly: string; whyImportant: string; askAstrologer: string; noData: string; loading: string;
  planetaryEvents: string; yourChart: string; currentDasha: string; significantFor: string;
  swissephMissing: string; noChartYet: string; house: string;
  auspiciousWindows: string; avoidTimes: string; sunrise: string; sunset: string;
  noMuhurtaData: string;
  currentLocation: string; useCurrentLocation: string; locationPermission: string; locationDenied: string;
  personalFavorable: string; personalNormal: string;
  enterLocationManually: string; manualPlaceholder: string; setLocation: string;
  manualLocating: string; manualNotFound: string; liveTracking: string; manualLocationLabel: string;
  switchToLive: string; usingCurrentLocation: string; locationUsedFor: string;
  favorableForYou: string; planetaryMovementsShort: string; dashaEventsShort: string; significantDatesShort: string;
}> = {
  English: {
    title: 'Astrology Calendar',
    filters: { all: 'All', transits: 'Transits', dasha: 'Dasha', important: 'For Me', career: 'Career', finance: 'Finance', marriage: 'Marriage', health: 'Health', education: 'Education' },
    monthAtGlance: 'at a Glance', significantDates: 'potentially significant dates',
    significantTransits: 'planetary movements', dashaEvents: 'Dasha-related events',
    mostSignificant: 'Most significant', viewMonthly: 'View Monthly Analysis',
    whyImportant: 'Why is this important?', askAstrologer: 'Ask Astrologer', noData: 'No events on this day.',
    loading: 'Loading...', planetaryEvents: 'Planetary Events', yourChart: 'Your Chart',
    currentDasha: 'Current Dasha', significantFor: 'Significant For You',
    swissephMissing: 'Transit calculations are not available yet on the server.',
    noChartYet: 'Chat with the astrologer once to unlock personalized relevance.', house: 'House',
    auspiciousWindows: "Today's Auspicious Windows", avoidTimes: 'Avoid These Times', sunrise: 'Sunrise', sunset: 'Sunset',
    noMuhurtaData: 'Timing calculations need a location — share your location below to unlock them.',
    currentLocation: 'Live location', useCurrentLocation: 'Refresh location', locationPermission: 'Getting your live location…', locationDenied: 'Using birth location',
    personalFavorable: 'Favorable', personalNormal: 'Normal',
    enterLocationManually: 'Enter location manually', manualPlaceholder: 'e.g. Lucknow, India',
    setLocation: 'Set', manualLocating: 'Finding…', manualNotFound: "Couldn't find that place — try a more specific name.",
    liveTracking: 'Live tracking on', manualLocationLabel: 'Manual location',
    switchToLive: 'Use live location instead',
    usingCurrentLocation: 'Using your current location',
    locationUsedFor: 'Used for sunrise, sunset and local Muhurta timings.',
    favorableForYou: 'favorable dates for you',
    planetaryMovementsShort: 'planetary movements',
    dashaEventsShort: 'Dasha events',
    significantDatesShort: 'significant dates',
  },
  Hindi: {
    title: 'ज्योतिष कैलेंडर',
    filters: { all: 'सभी', transits: 'गोचर', dasha: 'दशा', important: 'मेरे लिए', career: 'कैरियर', finance: 'वित्त', marriage: 'विवाह', health: 'स्वास्थ्य', education: 'शिक्षा' },
    monthAtGlance: 'की झलक', significantDates: 'संभावित महत्वपूर्ण तिथियाँ',
    significantTransits: 'ग्रह गोचर', dashaEvents: 'दशा से जुड़ी घटनाएँ',
    mostSignificant: 'सबसे महत्वपूर्ण', viewMonthly: 'मासिक विश्लेषण देखें',
    whyImportant: 'यह महत्वपूर्ण क्यों है?', askAstrologer: 'ज्योतिषी से पूछें', noData: 'इस दिन कोई घटना नहीं है।',
    loading: 'लोड हो रहा है...', planetaryEvents: 'ग्रह घटनाएँ', yourChart: 'आपकी कुंडली',
    currentDasha: 'वर्तमान दशा', significantFor: 'आपके लिए महत्वपूर्ण',
    swissephMissing: 'गोचर गणना अभी सर्वर पर उपलब्ध नहीं है।',
    noChartYet: 'व्यक्तिगत जानकारी के लिए पहले ज्योतिषी से एक बार बात करें।', house: 'भाव',
    auspiciousWindows: 'आज के शुभ मुहूर्त', avoidTimes: 'इन समयों से बचें', sunrise: 'सूर्योदय', sunset: 'सूर्यास्त',
    noMuhurtaData: 'मुहूर्त गणना के लिए स्थान चाहिए — नीचे अपना स्थान साझा करें।',
    currentLocation: 'लाइव स्थान', useCurrentLocation: 'स्थान रीफ्रेश करें', locationPermission: 'आपका लाइव स्थान प्राप्त किया जा रहा है…', locationDenied: 'जन्म स्थान उपयोग हो रहा है',
    personalFavorable: 'अनुकूल', personalNormal: 'सामान्य',
    enterLocationManually: 'स्थान मैन्युअल रूप से दर्ज करें', manualPlaceholder: 'जैसे लखनऊ, भारत',
    setLocation: 'सेट करें', manualLocating: 'खोजा जा रहा है…', manualNotFound: 'यह स्थान नहीं मिला — अधिक स्पष्ट नाम आज़माएं।',
    liveTracking: 'लाइव ट्रैकिंग चालू', manualLocationLabel: 'मैन्युअल स्थान',
    switchToLive: 'लाइव स्थान उपयोग करें',
    usingCurrentLocation: 'आपके वर्तमान स्थान का उपयोग',
    locationUsedFor: 'सूर्योदय, सूर्यास्त और स्थानीय मुहूर्त के लिए उपयोग किया जाता है।',
    favorableForYou: 'आपके लिए अनुकूल तिथियाँ',
    planetaryMovementsShort: 'ग्रह गोचर',
    dashaEventsShort: 'दशा घटनाएँ',
    significantDatesShort: 'महत्वपूर्ण तिथियाँ',
  },
  Hinglish: {
    title: 'Astrology Calendar',
    filters: { all: 'All', transits: 'Transits', dasha: 'Dasha', important: 'For Me', career: 'Career', finance: 'Finance', marriage: 'Marriage', health: 'Health', education: 'Education' },
    monthAtGlance: 'at a Glance', significantDates: 'potentially significant dates',
    significantTransits: 'planetary movements', dashaEvents: 'Dasha-related events',
    mostSignificant: 'Most significant', viewMonthly: 'View Monthly Analysis',
    whyImportant: 'Yeh important kyun hai?', askAstrologer: 'Astrologer se poochein', noData: 'Is din koi event nahi hai.',
    loading: 'Loading...', planetaryEvents: 'Planetary Events', yourChart: 'Aapki Kundli',
    currentDasha: 'Current Dasha', significantFor: 'Aapke liye significant',
    swissephMissing: 'Transit calculations abhi server par available nahi hain.',
    noChartYet: 'Personalized relevance ke liye pehle ek baar astrologer se baat karein.', house: 'House',
    auspiciousWindows: "Aaj Ke Shubh Muhurta", avoidTimes: 'Yeh Times Avoid Karein', sunrise: 'Sunrise', sunset: 'Sunset',
    noMuhurtaData: 'Timing calculations ke liye location chahiye — neeche apna location share karein.',
    currentLocation: 'Live location', useCurrentLocation: 'Location refresh karein', locationPermission: 'Aapka live location liya ja raha hai…', locationDenied: 'Birth location use ho rahi hai',
    personalFavorable: 'Favorable', personalNormal: 'Normal',
    enterLocationManually: 'Location manually daalein', manualPlaceholder: 'jaise Lucknow, India',
    setLocation: 'Set karein', manualLocating: 'Dhoondh rahe hain…', manualNotFound: 'Yeh jagah nahi mili — thoda specific naam try karein.',
    liveTracking: 'Live tracking ON', manualLocationLabel: 'Manual location',
    switchToLive: 'Live location use karein',
    usingCurrentLocation: 'Aapki current location use ho rahi hai',
    locationUsedFor: 'Sunrise, sunset aur local Muhurta timings ke liye use hoti hai.',
    favorableForYou: 'favorable dates aapke liye',
    planetaryMovementsShort: 'planetary movements',
    dashaEventsShort: 'Dasha events',
    significantDatesShort: 'significant dates',
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

  const [currentLocation, setCurrentLocation] = useState<{ latitude: number; longitude: number } | null>(null);
  const [locationLabel, setLocationLabel] = useState<string | null>(null);
  const [locationMode, setLocationMode] = useState<LocationMode>('geolocation');
  const [locationStatus, setLocationStatus] = useState<LocationStatus>('requesting');
  const [manualPlace, setManualPlace] = useState('');
  const [manualLabel, setManualLabel] = useState<string | null>(null);
  const [showManualInput, setShowManualInput] = useState(false);
  const watchIdRef = useRef<number | null>(null);

  const stopLiveTracking = useCallback(() => {
    if (watchIdRef.current !== null && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchIdRef.current);
      watchIdRef.current = null;
    }
  }, []);

  const startLiveTracking = useCallback(() => {
    if (!navigator.geolocation) {
      setLocationStatus('unsupported');
      setShowManualInput(true);
      return;
    }

    stopLiveTracking();
    setLocationMode('geolocation');
    setLocationStatus('requesting');
    setManualLabel(null);
    setLocationLabel(null);

    watchIdRef.current = navigator.geolocation.watchPosition(
      (position) => {
        setCurrentLocation({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
        setLocationStatus('ready');
        setShowManualInput(false);
      },
      (error) => {
        console.warn('Live location unavailable:', error.message);
        setLocationStatus(error.code === error.PERMISSION_DENIED ? 'denied' : 'unsupported');
        setShowManualInput(true);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  }, [stopLiveTracking]);

  useEffect(() => {
    startLiveTracking();
    return () => stopLiveTracking();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Resolve live coordinates into a real place name (e.g. "Guntakal,
  // Andhra Pradesh") instead of showing raw lat/lon to the user. Manual
  // entries already carry a human-typed label (manualLabel), so this only
  // runs for the geolocation path.
  useEffect(() => {
    if (!currentLocation || !sessionId || locationMode !== 'geolocation') return;
    let cancelled = false;
    fetch(`${API_BASE}/session/${sessionId}/calendar/reverse-geocode?latitude=${encodeURIComponent(currentLocation.latitude)}&longitude=${encodeURIComponent(currentLocation.longitude)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && data?.label) setLocationLabel(data.label);
      })
      .catch(() => {
        // Silent — falls back to the generic "Live location" label.
      });
    return () => { cancelled = true; };
  }, [currentLocation, sessionId, locationMode]);

  const handleSetManualLocation = async () => {
    const place = manualPlace.trim();
    if (!place || !sessionId) return;

    stopLiveTracking();
    setLocationMode('manual');
    setLocationStatus('manual_pending');

    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/calendar/geocode?place=${encodeURIComponent(place)}`);
      if (!res.ok) {
        setLocationStatus('manual_error');
        return;
      }
      const data = await res.json();
      setCurrentLocation({ latitude: data.latitude, longitude: data.longitude });
      setManualLabel(place);
      setLocationStatus('ready');
      setShowManualInput(false);
    } catch (err) {
      console.error('Manual geocoding failed:', err);
      setLocationStatus('manual_error');
    }
  };

  const switchBackToLive = () => {
    setManualLabel(null);
    startLiveTracking();
  };

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

  // ------------------------------------------------------------------
  // FILTERS
  // All | Transits | Dasha | For Me | Career | Finance | Marriage |
  // Health | Education
  //
  // House-wise filters use the backend's existing transit relevance data.
  // A day matches a topic when one of that day's transit events is tagged
  // with the selected topic in event.relevance.topics.
  // ------------------------------------------------------------------
  const transitMatchesTopic = (
    info: DayInfo,
    topic: Exclude<FilterKey, 'all' | 'transits' | 'dasha' | 'important'>
  ): boolean => {
    const keywords = HOUSE_TOPIC_FILTERS[topic];

    return info.transits.some((event) =>
      event.relevance?.topics?.some((eventTopic) => {
        const normalized = eventTopic.toLowerCase().trim();
        return keywords.some((keyword) =>
          normalized === keyword || normalized.includes(keyword) || keyword.includes(normalized)
        );
      })
    );
  };

  const dayMatchesFilter = (info: DayInfo): boolean => {
    switch (filter) {
      case 'transits':
        return info.transits.length > 0;
      case 'dasha':
        return info.dasha.length > 0;
      case 'important':
        return info.personal_status === 'favorable';
      case 'career':
      case 'finance':
      case 'marriage':
      case 'health':
      case 'education':
        return transitMatchesTopic(info, filter);
      default:
        return true;
    }
  };

  const isFavorable = (info?: DayInfo) => info?.personal_status === 'favorable';

  const personalStatusLabel = (status?: 'favorable' | 'normal' | null) => {
    if (status === 'favorable') return t.personalFavorable;
    return t.personalNormal;
  };

  const daysInMonth = new Date(year, month, 0).getDate();
  const firstOfMonth = new Date(year, month - 1, 1);
  const leadingBlanks = (firstOfMonth.getDay() + 6) % 7; // Monday-start offset

  const cells: (number | null)[] = [
    ...Array(leadingBlanks).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  const locationTitle = locationMode === 'manual' && manualLabel
    ? `${t.manualLocationLabel}: ${manualLabel}`
    : locationStatus === 'ready'
      ? (locationLabel ? `${t.usingCurrentLocation}: ${locationLabel}` : t.currentLocation)
      : locationStatus === 'requesting'
        ? t.locationPermission
        : t.locationDenied;

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

          {/* Location card — live tracker + manual fallback */}
          <div className="bg-white border border-slate-200 rounded-xl px-3 py-2.5">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                {locationMode === 'geolocation' && locationStatus === 'ready' ? (
                  <Navigation size={15} className="text-emerald-500 shrink-0" />
                ) : (
                  <MapPin size={15} className="text-amber-500 shrink-0" />
                )}
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-slate-700 truncate">{locationTitle}</p>
                  {locationStatus === 'ready' && (
                    <p className="text-[10px] text-slate-400 truncate">{t.locationUsedFor}</p>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-1.5 shrink-0">
                {locationMode === 'geolocation' ? (
                  <button
                    type="button"
                    onClick={startLiveTracking}
                    disabled={locationStatus === 'requesting'}
                    className="flex items-center gap-1.5 text-[11px] font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-lg px-2.5 py-1.5 disabled:opacity-50"
                  >
                    <RefreshCw size={12} className={locationStatus === 'requesting' ? 'animate-spin' : ''} />
                    {t.useCurrentLocation}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={switchBackToLive}
                    className="flex items-center gap-1.5 text-[11px] font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded-lg px-2.5 py-1.5"
                  >
                    <Navigation size={12} />
                    {t.switchToLive}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setShowManualInput((v) => !v)}
                  className="flex items-center gap-1.5 text-[11px] font-medium text-slate-600 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg px-2.5 py-1.5"
                >
                  <Search size={12} />
                  {t.enterLocationManually}
                </button>
              </div>
            </div>

            {showManualInput && (
              <div className="mt-2.5 pt-2.5 border-t border-slate-100 flex gap-2">
                <input
                  value={manualPlace}
                  onChange={(e) => setManualPlace(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSetManualLocation()}
                  placeholder={t.manualPlaceholder}
                  className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-xs"
                />
                <button
                  type="button"
                  onClick={handleSetManualLocation}
                  disabled={!manualPlace.trim() || locationStatus === 'manual_pending'}
                  className="px-3 py-2 rounded-lg text-xs font-semibold bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50 transition shrink-0"
                >
                  {locationStatus === 'manual_pending' ? t.manualLocating : t.setLocation}
                </button>
              </div>
            )}
            {locationStatus === 'manual_error' && (
              <p className="text-[11px] text-rose-500 mt-1.5">{t.manualNotFound}</p>
            )}
          </div>

          {/* Filters — All | Transits | Dasha | For Me | Career | Finance | Marriage | Health | Education */}
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

                  const favorable = isFavorable(info);
                  const hasTransit = !!info?.transits?.length;
                  const hasDasha = !!info?.dasha?.length;
                  const isToday = year === today.getFullYear() && month === today.getMonth() + 1 && day === today.getDate();

                  const showTransitDot = (filter === 'all' || filter === 'transits') && hasTransit;
                  const showDashaDot = (filter === 'all' || filter === 'dasha') && hasDasha;
                  const showFavorableDot = (filter === 'all' || filter === 'important') && favorable;

                  const careerDot = filter === 'career' && !!info && transitMatchesTopic(info, 'career');
                  const financeDot = filter === 'finance' && !!info && transitMatchesTopic(info, 'finance');
                  const marriageDot = filter === 'marriage' && !!info && transitMatchesTopic(info, 'marriage');
                  const healthDot = filter === 'health' && !!info && transitMatchesTopic(info, 'health');
                  const educationDot = filter === 'education' && !!info && transitMatchesTopic(info, 'education');
                  return (
                    <button
                      key={day}
                      onClick={() => openDay(day)}
                      title={filter === 'important' ? personalStatusLabel(info?.personal_status) : undefined}
                      className={`aspect-square rounded-lg flex flex-col items-center justify-center text-xs relative transition
                        ${selectedDay === day ? 'bg-amber-500 text-white' : isToday ? 'bg-amber-50 text-amber-700 font-semibold' : 'hover:bg-slate-50 text-slate-700'}
                        ${!visible && filter !== 'all' ? 'opacity-30' : ''}`}
                    >
                      <span>{day}</span>
                      <span className="flex gap-0.5 mt-0.5">
                        {showFavorableDot && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-emerald-500'}`} />}
                        {showTransitDot && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-sky-500'}`} />}
                        {showDashaDot && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-violet-500'}`} />}
                        {careerDot && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-emerald-500'}`} />}
                        {financeDot && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-emerald-500'}`} />}
                        {marriageDot && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-emerald-500'}`} />}
                        {educationDot && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-emerald-500'}`} />}
                        {healthDot && <span className={`w-1 h-1 rounded-full ${selectedDay === day ? 'bg-white' : 'bg-emerald-500'}`} />}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}

            {/* Legend — matches exactly which dots are visible for the active filter */}
            {!loading && filter === 'important' && (
              <div className="flex flex-wrap gap-3 mt-4 pt-3 border-t border-slate-100 text-[10px] text-slate-500">
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> {t.personalFavorable}</span>
              </div>
            )}
            {!loading && filter === 'all' && (
              <div className="flex flex-wrap gap-3 mt-4 pt-3 border-t border-slate-100 text-[10px] text-slate-400">
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> {t.personalFavorable}</span>
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-sky-500" /> {t.significantTransits}</span>
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-violet-500" /> {t.dashaEvents}</span>
              </div>
            )}
            {!loading && filter === 'transits' && (
              <div className="flex flex-wrap gap-3 mt-4 pt-3 border-t border-slate-100 text-[10px] text-slate-400">
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-sky-500" /> {t.significantTransits}</span>
              </div>
            )}
            {!loading && filter === 'dasha' && (
              <div className="flex flex-wrap gap-3 mt-4 pt-3 border-t border-slate-100 text-[10px] text-slate-400">
                <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-violet-500" /> {t.dashaEvents}</span>
              </div>
            )}

            {(!loading && ['career', 'finance', 'marriage', 'health', 'education'].includes(filter)) && (
              <div className="flex flex-wrap gap-3 mt-4 pt-3 border-t border-slate-100 text-[10px] text-slate-500">
                <span className="flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                  {t.personalFavorable}
                </span>
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
                {dayDetail?.location_source === 'current'
                  ? (locationMode === 'manual' && manualLabel ? `${t.manualLocationLabel}: ${manualLabel}` : (locationLabel || t.currentLocation))
                  : t.locationDenied}
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

                  {dayDetail.muhurta && (dayDetail.muhurta.abhijit.length > 0 || dayDetail.muhurta.brahma.length > 0) && (
                    <MuhurtaSection title={t.auspiciousWindows} items={[
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
                        : 'bg-slate-50 border-slate-200 text-slate-600'
                    }`}>
                      <p className="text-[10px] uppercase tracking-wide font-semibold mb-1">
                        {t.significantFor}
                      </p>
                      <p className="text-xs font-medium">
                        {personalStatusLabel(dayDetail.personal_status)}
                      </p>
                      {dayDetail.personal_supportive_reasons?.length ? (
                        <p className="text-[11px] mt-1">{dayDetail.personal_supportive_reasons.join(' • ')}</p>
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

          {/* Month at a Glance */}
          {!loading && summary && (
            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
              <h3 className="text-sm font-bold text-slate-800 mb-3">
                {MONTH_NAMES[month - 1]} {year} {t.monthAtGlance}
              </h3>
              <ul className="text-sm text-slate-700 space-y-1.5">
                <li>🟢 {summary.favorable_days} {t.favorableForYou}</li>
                <li>🔵 {summary.transit_count} {t.planetaryMovementsShort}</li>
                <li>🟣 {summary.dasha_event_count} {t.dashaEventsShort}</li>
                <li>⭐ {summary.significant_day_count} {t.significantDatesShort}</li>
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