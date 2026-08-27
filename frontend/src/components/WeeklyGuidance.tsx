import { useEffect, useState } from 'react';

const API_BASE =
  ((import.meta as ImportMeta & {
    env?: { VITE_API_BASE?: string }
  }).env?.VITE_API_BASE) || '/api';

interface WeeklyGuidanceProps {
  sessionId: string;
  language: string;
}

const STRINGS: Record<string, {
  title: string;
  loading: string;
  emptyState: string;
  errorState: string;
}> = {
  English: {
    title: "This Week's Guidance",
    loading: 'Loading...',
    emptyState: 'Chat with the astrologer once to unlock your weekly guidance.',
    errorState: 'Could not load weekly guidance. Please try again later.',
  },
  Hindi: {
    title: 'इस सप्ताह का मार्गदर्शन',
    loading: 'लोड हो रहा है...',
    emptyState: 'अपना साप्ताहिक मार्गदर्शन अनलॉक करने के लिए एक बार ज्योतिषी से बात करें।',
    errorState: 'साप्ताहिक मार्गदर्शन लोड नहीं हो सका। कृपया बाद में पुनः प्रयास करें।',
  },
  Hinglish: {
    title: 'Is Hafte Ka Margdarshan',
    loading: 'Loading...',
    emptyState: 'Apna weekly guidance unlock karne ke liye ek baar astrologer se baat karein.',
    errorState: 'Weekly guidance load nahi ho saka. Kripya baad mein dobara koshish karein.',
  },
};

export default function WeeklyGuidance({ sessionId, language }: WeeklyGuidanceProps) {
  const [guidance, setGuidance] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const t = STRINGS[language] || STRINGS.Hinglish;

  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    setError(false);

    fetch(`${API_BASE}/session/${sessionId}/weekly-guidance`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load weekly guidance');
        return res.json();
      })
      .then((data) => {
        if (data.available) {
          setGuidance(data.guidance);
        } else {
          setGuidance(null);
        }
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [sessionId]);

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-3">{t.title}</h3>
      <p className="text-sm text-slate-800 leading-relaxed">
        {loading ? t.loading : error ? t.errorState : guidance || t.emptyState}
      </p>
    </div>
  );
}