import { useEffect, useState } from 'react';
const API_BASE =
  ((import.meta as ImportMeta & {
    env?: { VITE_API_BASE?: string }
  }).env?.VITE_API_BASE) || '/api';
import {
  Sparkles,
  ChevronDown,
  ChevronUp,
  BookOpen,
  CircleUserRound,
  Clock3,
  ShieldCheck,
  Brain,
} from 'lucide-react';

interface TraceStep {
  step: number;
  title: string;
  detail: string;
  type?: 'rag' | 'chart' | 'dasha' | 'evidence' | 'synthesis' | 'general';
}

interface ReasoningTraceProps {
  sessionId: string;
  refreshKey: number;
  language: string;
}

const STRINGS: Record<
  string,
  {
    title: string;
    empty: string;
    collapse: string;
    expand: string;
  }
> = {
  English: {
    title: 'How I Reached This',
    empty: 'Ask a question to see the reasoning behind the reading.',
    collapse: 'Collapse',
    expand: 'Expand',
  },

  Hindi: {
    title: 'यह निष्कर्ष कैसे निकला',
    empty: 'तर्क देखने के लिए एक प्रश्न पूछें।',
    collapse: 'छोटा करें',
    expand: 'बड़ा करें',
  },

  Hinglish: {
    title: 'Yeh Reading Kaise Bani',
    empty: 'Reasoning dekhne ke liye ek sawaal poochein.',
    collapse: 'Chota karein',
    expand: 'Bada karein',
  },
};

const STEP_ICONS = {
  rag: BookOpen,
  chart: CircleUserRound,
  dasha: Clock3,
  evidence: ShieldCheck,
  synthesis: Brain,
  general: Sparkles,
};

export default function ReasoningTrace({
  sessionId,
  refreshKey,
  language,
}: ReasoningTraceProps) {
  const [steps, setSteps] = useState<TraceStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(true);

  const t = STRINGS[language] || STRINGS.Hinglish;

  useEffect(() => {
    if (!sessionId) return;

    setLoading(true);

    fetch(`${API_BASE}/session/${sessionId}/reasoning-trace`)
      .then((res) => {
        if (!res.ok) {
          throw new Error('Failed to fetch reasoning trace');
        }
        return res.json();
      })
      .then((data) => {
        setSteps(data.available ? data.steps || [] : []);
      })
      .catch(() => {
        setSteps([]);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [sessionId, refreshKey]);

  return (
    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-slate-50 transition"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-amber-500" />

          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
            {t.title}
          </h3>
        </div>

        {expanded ? (
          <ChevronUp size={14} className="text-slate-400" />
        ) : (
          <ChevronDown size={14} className="text-slate-400" />
        )}
      </button>

      {/* Content */}
      {expanded && (
        <div className="px-5 pb-5">
          {loading ? (
            <div className="space-y-3 animate-pulse">
              <div className="flex gap-3">
                <div className="w-7 h-7 bg-slate-100 rounded-full" />
                <div className="flex-1 space-y-2">
                  <div className="h-3 bg-slate-100 rounded w-3/4" />
                  <div className="h-3 bg-slate-100 rounded w-1/2" />
                </div>
              </div>

              <div className="flex gap-3">
                <div className="w-7 h-7 bg-slate-100 rounded-full" />
                <div className="flex-1 space-y-2">
                  <div className="h-3 bg-slate-100 rounded w-2/3" />
                  <div className="h-3 bg-slate-100 rounded w-1/2" />
                </div>
              </div>

              <div className="flex gap-3">
                <div className="w-7 h-7 bg-slate-100 rounded-full" />
                <div className="flex-1 space-y-2">
                  <div className="h-3 bg-slate-100 rounded w-3/4" />
                  <div className="h-3 bg-slate-100 rounded w-1/3" />
                </div>
              </div>
            </div>
          ) : steps.length === 0 ? (
            <p className="text-xs text-slate-400 italic">
              {t.empty}
            </p>
          ) : (
            <ol className="space-y-4">
              {steps.map((s, index) => {
                const Icon =STEP_ICONS[s.type as keyof typeof STEP_ICONS] || Sparkles;
                return (
                  <li
                    key={`${s.step}-${index}`}
                    className="flex gap-3"
                  >
                    {/* Step icon */}
                    <div className="shrink-0 w-7 h-7 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center mt-0.5">
                      <Icon size={14} />
                    </div>

                    {/* Step content */}
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-semibold text-slate-700">
                        {s.step}. {s.title}
                      </div>

                      <div className="text-xs text-slate-500 mt-1 leading-relaxed whitespace-pre-line">
                        {s.detail}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}