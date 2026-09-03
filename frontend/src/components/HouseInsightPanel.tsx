import { useEffect, useState } from 'react';
import { X } from 'lucide-react';

const API_BASE =
  ((import.meta as ImportMeta & {
    env?: { VITE_API_BASE?: string }
  }).env?.VITE_API_BASE) || '/api';

interface HouseInsightPanelProps {
  sessionId: string;
  houseNumber: number | null;
  language: string;
  onClose: () => void;
}

interface HouseInsightData {
  available: boolean;
  house_number?: number;
  sign?: string;
  lord?: string;
  occupants?: string[];
  theme?: string;
  current_dasha?: string | null;
  explanation?: string;
  reason?: string;
}

const STRINGS: Record<string, {
  houseLabel: string;
  loading: string;
  errorState: string;
  notAvailable: string;
  signLabel: string;
  lordLabel: string;
  occupantsLabel: string;
  noOccupants: string;
  dashaLabel: string;
}> = {
  English: {
    houseLabel: 'House',
    loading: 'Reading your chart...',
    errorState: 'Could not load this house right now. Please try again.',
    notAvailable: 'Your chart isn\'t ready yet. Please chat with the astrologer once first.',
    signLabel: 'Sign',
    lordLabel: 'Lord',
    occupantsLabel: 'Planets here',
    noOccupants: 'None',
    dashaLabel: 'Current period',
  },
  Hindi: {
    houseLabel: 'भाव',
    loading: 'आपकी कुंडली पढ़ी जा रही है...',
    errorState: 'अभी यह भाव लोड नहीं हो सका। कृपया दोबारा प्रयास करें।',
    notAvailable: 'आपकी कुंडली अभी तैयार नहीं है। पहले एक बार ज्योतिषी से बात करें।',
    signLabel: 'राशि',
    lordLabel: 'स्वामी',
    occupantsLabel: 'यहाँ ग्रह',
    noOccupants: 'कोई नहीं',
    dashaLabel: 'वर्तमान दशा',
  },
  Hinglish: {
    houseLabel: 'House',
    loading: 'Aapki kundali padhi ja rahi hai...',
    errorState: 'Abhi yeh house load nahi ho saka. Kripya dobara koshish karein.',
    notAvailable: 'Aapki kundali abhi taiyaar nahi hai. Pehle ek baar astrologer se baat karein.',
    signLabel: 'Sign',
    lordLabel: 'Lord',
    occupantsLabel: 'Yahaan grah',
    noOccupants: 'Koi nahi',
    dashaLabel: 'Current period',
  },
};

export default function HouseInsightPanel({ sessionId, houseNumber, language, onClose }: HouseInsightPanelProps) {
  const [data, setData] = useState<HouseInsightData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const t = STRINGS[language] || STRINGS.Hinglish;

  useEffect(() => {
    if (houseNumber === null || !sessionId) return;
    setLoading(true);
    setError(false);
    setData(null);

    fetch(`${API_BASE}/session/${sessionId}/house-insight/${houseNumber}`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load house insight');
        return res.json();
      })
      .then((result: HouseInsightData) => setData(result))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [sessionId, houseNumber]);

  if (houseNumber === null) return null;

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 px-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl p-6 w-full max-w-md shadow-lg max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-slate-800">
            {t.houseLabel} {houseNumber}
            {data?.theme ? <span className="block text-xs font-normal text-slate-400 mt-0.5 capitalize">{data.theme}</span> : null}
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 p-1">
            <X size={18} />
          </button>
        </div>

        {loading && <p className="text-sm text-slate-400">{t.loading}</p>}
        {!loading && error && <p className="text-sm text-rose-500">{t.errorState}</p>}

        {!loading && !error && data && !data.available && (
          <p className="text-sm text-slate-400">{t.notAvailable}</p>
        )}

        {!loading && !error && data?.available && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="bg-slate-50 rounded-lg p-2.5">
                <div className="text-slate-400 font-medium">{t.signLabel}</div>
                <div className="text-slate-800 font-semibold mt-0.5">{data.sign || '—'}</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-2.5">
                <div className="text-slate-400 font-medium">{t.lordLabel}</div>
                <div className="text-slate-800 font-semibold mt-0.5">{data.lord || '—'}</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-2.5 col-span-2">
                <div className="text-slate-400 font-medium">{t.occupantsLabel}</div>
                <div className="text-slate-800 font-semibold mt-0.5">
                  {data.occupants && data.occupants.length > 0 ? data.occupants.join(', ') : t.noOccupants}
                </div>
              </div>
              {data.current_dasha && (
                <div className="bg-amber-50 rounded-lg p-2.5 col-span-2">
                  <div className="text-amber-600 font-medium">{t.dashaLabel}</div>
                  <div className="text-amber-800 font-semibold mt-0.5">{data.current_dasha}</div>
                </div>
              )}
            </div>

            <p className="text-sm text-slate-700 leading-relaxed border-t border-slate-100 pt-3">
              {data.explanation}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}