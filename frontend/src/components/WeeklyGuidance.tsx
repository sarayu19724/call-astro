import { useEffect, useState } from 'react';
const API_BASE =
  ((import.meta as ImportMeta & {
    env?: { VITE_API_BASE?: string }
  }).env?.VITE_API_BASE) || '/api';
  
interface WeeklyGuidanceProps {
  sessionId: string;
}

export default function WeeklyGuidance({ sessionId }: WeeklyGuidanceProps) {
  const [guidance, setGuidance] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/session/${sessionId}/weekly-guidance`)
      .then((res) => res.json())
      .then((data) => {
        if (data.available) setGuidance(data.guidance);
      })
      .finally(() => setLoading(false));
  }, [sessionId]);

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-3">
        This Week's Guidance
      </h3>
      <p className="text-sm text-slate-800 leading-relaxed">
        {loading ? 'Loading...' : guidance || 'Chat once to unlock your weekly guidance.'}
      </p>
    </div>
  );
}