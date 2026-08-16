import { useEffect, useState } from 'react';

interface LifeDashboardProps {
  sessionId: string;
  language: string;
}

const STRINGS: Record<string, {
  title: string;
  loading: string;
  emptyState: string;
  luckyColorLabel: string;
  notAvailable: string;
}> = {
  English: {
    title: "Today's Reflection",
    loading: 'Loading...',
    emptyState: 'Chat with the astrologer once to unlock your daily reflection.',
    luckyColorLabel: 'Lucky Colour Today',
    notAvailable: 'N/A',
  },
  Hindi: {
    title: 'आज का विचार',
    loading: 'लोड हो रहा है...',
    emptyState: 'अपना दैनिक विचार अनलॉक करने के लिए एक बार ज्योतिषी से बात करें।',
    luckyColorLabel: 'आज का शुभ रंग',
    notAvailable: 'उपलब्ध नहीं',
  },
  Hinglish: {
    title: 'Aaj Ka Vichar',
    loading: 'Loading...',
    emptyState: 'Apna daily reflection unlock karne ke liye ek baar astrologer se baat karein.',
    luckyColorLabel: 'Aaj Ka Lucky Colour',
    notAvailable: 'N/A',
  },
};

export default function LifeDashboard({ sessionId, language }: LifeDashboardProps) {
  const [prediction, setPrediction] = useState<string | null>(null);
  const [luckyColor, setLuckyColor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const t = STRINGS[language] || STRINGS.Hinglish;

  useEffect(() => {
    fetch(`/api/session/${sessionId}/dashboard`)
      .then((res) => res.json())
      .then((data) => {
        if (data.available) {
          setPrediction(data.prediction);
          setLuckyColor(data.lucky_color);
        }
      })
      .finally(() => setLoading(false));
  }, [sessionId]);

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-3">{t.title}</h3>
      <p className="text-sm text-slate-800 leading-relaxed mb-4">
        {loading ? t.loading : prediction || t.emptyState}
      </p>
      <div className="flex items-center justify-between pt-3 border-t border-slate-100">
        <span className="text-xs font-medium text-slate-400">{t.luckyColorLabel}</span>
        <span className="text-sm font-semibold text-slate-800">{loading ? '...' : luckyColor || t.notAvailable}</span>
      </div>
    </div>
  );
}