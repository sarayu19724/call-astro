import {  useState } from 'react';
import { ChevronDown, ChevronUp, Sparkles, Home, Search, Clock, BookOpen, Scale, GitBranch, CheckCircle2, ListChecks } from 'lucide-react';

interface ReasoningStep {
  step: number;
  title: string;
  detail: string;
  type: string;
}

interface ReasoningTraceProps {
  sessionId: string;
}

const STEP_ICONS: Record<string, React.ReactNode> = {
  query_understanding: <Sparkles size={16} />,
  rag: <BookOpen size={16} />,
  chart: <Home size={16} />,
  buckets: <ListChecks size={16} />,
  fact_rule_table: <CheckCircle2 size={16} />,
  sufficiency: <Scale size={16} />,
  personalized_rag: <Search size={16} />,
  consensus: <Scale size={16} />,
  contradiction: <GitBranch size={16} />,
  dasha: <Clock size={16} />,
  evidence: <BookOpen size={16} />,
  synthesis: <Scale size={16} />,
  specificity: <CheckCircle2 size={16} />,
  claim_mapping: <ListChecks size={16} />,
};

const CONSENSUS_STYLES: Record<string, string> = {
  HIGH: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  MEDIUM: 'bg-amber-50 text-amber-700 border-amber-200',
  LOW: 'bg-slate-100 text-slate-500 border-slate-200',
  CONFLICTING: 'bg-rose-50 text-rose-700 border-rose-200',
};

function extractConsensusLabel(detail: string): string | null {
  const match = detail.match(/Evidence confidence:\s*(HIGH|MEDIUM|LOW|CONFLICTING)/i);
  return match ? match[1].toUpperCase() : null;
}

function hasContradiction(detail: string): boolean {
  return detail.startsWith('CONTRADICTION DETECTED');
}

export default function ReasoningTrace({ sessionId }: ReasoningTraceProps) {
  const [steps, setSteps] = useState<ReasoningStep[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const fetchTrace = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/session/${sessionId}/reasoning-trace`);
      if (res.ok) {
        const data = await res.json();
        setSteps(data.steps || data.trace || []);
      }
    } catch (err) {
      console.error('Failed to load reasoning trace:', err);
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  };

  const handleToggle = () => {
    if (!expanded && !loaded) {
      fetchTrace();
    }
    setExpanded(!expanded);
  };

  if (!sessionId) return null;

  return (
    <div className="mt-2">
      <button
        onClick={handleToggle}
        className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-700 transition"
      >
        <Sparkles size={12} />
        How I reached this
        {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      {expanded && (
        <div className="mt-2 bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
          {loading && (
            <p className="text-xs text-slate-400">Loading reasoning trace...</p>
          )}

          {!loading && steps.length === 0 && (
            <p className="text-xs text-slate-400">No detailed reasoning trace available for this response.</p>
          )}

          {!loading && steps.map((s) => {
            const consensusLabel = s.type === 'consensus' ? extractConsensusLabel(s.detail) : null;
            const isContradiction = s.type === 'contradiction' && hasContradiction(s.detail);
            return (
              <div key={s.step} className="flex gap-2.5">
                <div className="w-6 h-6 rounded-full bg-white border border-slate-200 flex items-center justify-center text-slate-500 shrink-0 mt-0.5">
                  {STEP_ICONS[s.type] || <span className="text-[10px] font-bold">{s.step}</span>}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-semibold text-slate-700">
                      {s.step}. {s.title}
                    </span>
                    {consensusLabel && (
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${CONSENSUS_STYLES[consensusLabel] || CONSENSUS_STYLES.LOW}`}>
                        {consensusLabel} CONFIDENCE
                      </span>
                    )}
                    {isContradiction && (
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border bg-amber-50 text-amber-700 border-amber-200">
                        CONFLICT RESOLVED
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5 whitespace-pre-wrap leading-relaxed">
                    {s.detail}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}