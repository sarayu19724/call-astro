import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Heart, Loader2, RotateCcw, Send } from 'lucide-react';
import KundliChartToggle from './KundliChartToggle';

const API_BASE =
  ((import.meta as ImportMeta & { env?: { VITE_API_BASE?: string } }).env?.VITE_API_BASE) || '/api';

interface CouplePageProps {
  language: string;
  onBack: () => void;
}

interface PartnerForm {
  name: string;
  dob: string;
  birthTime: string;
  birthPlace: string;
}

interface PartnerStatusView {
  status: 'idle' | 'pending' | 'ready' | 'failed';
  error: string | null;
  name: string | null;
  dob: string | null;
  birth_time: string | null;
  birth_place: string | null;
  planets: any[] | null;
  ascendant_sign: string | null;
  current_dasha: any;
}

interface PlanetAssessment {
  planet: string;
  sign: string;
  house: number | null;
  retro: boolean;
  dignity_label: string;
  house_category: string | null;
  combined_score: number;
  verdict: string;
  reason: string;
  lordships?: number[];
}

interface ChildbirthFacts {
  house_number: number;
  sign: string | null;
  lord: string | null;
  occupants: { name: string; retro: boolean }[];
  lord_assessment: PlanetAssessment | null;
  significator_assessment: PlanetAssessment | null;
  benefic_occupants: string[];
  malefic_occupants: string[];
}

interface PartnerReport {
  facts: ChildbirthFacts;
  verdict: string;
  current_dasha: string | null;
  favorable_periods: { mahadasha: string; antardasha: string; start: string; end: string }[];
}

interface ChildbirthAnalysis {
  partner1_name: string;
  partner2_name: string;
  partner1_report: PartnerReport;
  partner2_report: PartnerReport;
  joint: {
    joint_verdict: string;
    overlapping_windows: { start: string; end: string; partner_a_period: string; partner_b_period: string }[];
    common_factors: string[];
    conflicting_factors: string[];
  };
}

interface ChatMsg {
  role: string;
  content: string;
}

const VERDICT_STYLES: Record<string, string> = {
  favorable: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  challenging: 'bg-rose-50 text-rose-700 border-rose-200',
  mixed: 'bg-amber-50 text-amber-700 border-amber-200',
  neutral: 'bg-slate-100 text-slate-500 border-slate-200',
};

const emptyPartner: PartnerForm = { name: '', dob: '', birthTime: '', birthPlace: '' };

export default function CouplePage({ language, onBack }: CouplePageProps) {
  const [step, setStep] = useState<'form' | 'loading' | 'dashboard'>('form');
  const [coupleId, setCoupleId] = useState<string>('');
  const [p1Form, setP1Form] = useState<PartnerForm>(emptyPartner);
  const [p2Form, setP2Form] = useState<PartnerForm>(emptyPartner);
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [p1, setP1] = useState<PartnerStatusView | null>(null);
  const [p2, setP2] = useState<PartnerStatusView | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [childbirth, setChildbirth] = useState<ChildbirthAnalysis | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatSending, setChatSending] = useState(false);

  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollingFor = useRef<string | null>(null);

  useEffect(() => () => {
    if (pollTimer.current) clearTimeout(pollTimer.current);
  }, []);

  const stopPolling = () => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  };

  const pollStatus = (cid: string) => {
    stopPolling();
    pollingFor.current = cid;
    let attempts = 0;

    const tick = async () => {
      if (pollingFor.current !== cid) return;
      try {
        const res = await fetch(`${API_BASE}/couple/${cid}/status`);
        if (res.ok) {
          const data = await res.json();
          if (pollingFor.current !== cid) return;
          setP1(data.partner1);
          setP2(data.partner2);

          if (data.partner1.status === 'failed' || data.partner2.status === 'failed') {
            setLoadError(data.partner1.error || data.partner2.error || 'Chart calculation failed.');
            return;
          }

          if (data.both_ready) {
            setStep('dashboard');
            fetchChildbirth(cid);
            fetchChatHistory(cid);
            return;
          }
        }
      } catch (err) {
        console.error('Couple status poll failed:', err);
      }

      attempts += 1;
      if (attempts >= 90) {
        setLoadError('This is taking longer than expected. Please retry.');
        return;
      }
      pollTimer.current = setTimeout(tick, 3000);
    };

    tick();
  };

  const fetchChildbirth = async (cid: string) => {
    try {
      const res = await fetch(`${API_BASE}/couple/${cid}/childbirth`);
      if (res.ok) {
        const data = await res.json();
        if (data.available) {
          const { available, ...rest } = data;
          setChildbirth(rest as ChildbirthAnalysis);
        }
      }
    } catch (err) {
      console.error('Failed to load childbirth analysis:', err);
    }
  };

  const fetchChatHistory = async (cid: string) => {
    try {
      const res = await fetch(`${API_BASE}/couple/${cid}/chat/history`);
      if (res.ok) {
        const data = await res.json();
        setChatMessages(data.messages || []);
      }
    } catch (err) {
      console.error('Failed to load couple chat history:', err);
    }
  };

  const validateForm = (): boolean => {
    for (const p of [p1Form, p2Form]) {
      if (!p.name.trim() || !p.dob || !p.birthTime || !p.birthPlace.trim()) {
        return false;
      }
    }
    return true;
  };

  const handleStartTest = async () => {
    setFormError('');
    if (!validateForm()) {
      setFormError("Please fill in both partners' full birth details.");
      return;
    }

    setSubmitting(true);
    try {
      const createRes = await fetch(`${API_BASE}/couple`, { method: 'POST' });
      if (!createRes.ok) throw new Error('Could not start couple test.');
      const { couple_id } = await createRes.json();
      setCoupleId(couple_id);

      const toApiDate = (d: PartnerForm) => {
        const [year, month, day] = d.dob.split('-');
        return `${day}-${month}-${year}`;
      };

      const submitPartner = (which: number, form: PartnerForm) =>
        fetch(`${API_BASE}/couple/${couple_id}/partner/${which}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: form.name.trim(),
            dob: toApiDate(form),
            birth_time: form.birthTime,
            birth_place: form.birthPlace.trim(),
          }),
        });

      const [r1, r2] = await Promise.all([submitPartner(1, p1Form), submitPartner(2, p2Form)]);
      if (!r1.ok || !r2.ok) throw new Error('Could not start chart calculation for one or both partners.');

      setStep('loading');
      setLoadError(null);
      pollStatus(couple_id);
    } catch (err: any) {
      setFormError(err.message || 'Something went wrong.');
    } finally {
      setSubmitting(false);
    }
  };
  const [knownOutcome, setKnownOutcome] = useState('');
  const [outcomeSaved, setOutcomeSaved] = useState(false);

  const handleSaveOutcome = async () => {
   if (!coupleId) return;
   try {
    const res = await fetch(`${API_BASE}/couple/${coupleId}/known-outcome`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ outcome: knownOutcome.trim() }),
    });
     if (res.ok) {
      setOutcomeSaved(true);
      setTimeout(() => setOutcomeSaved(false), 2000);
    }
  }  catch (err) {
    console.error('Failed to save known outcome:', err);
  }
};
  const retryLoading = () => {
    if (!coupleId) return;
    setLoadError(null);
    pollStatus(coupleId);
  };

  const handleReset = () => {
    stopPolling();
    pollingFor.current = null;
    setStep('form');
    setCoupleId('');
    setP1(null);
    setP2(null);
    setChildbirth(null);
    setChatMessages([]);
    setLoadError(null);
    setP1Form(emptyPartner);
    setP2Form(emptyPartner);
  };

  const handleSendChat = async () => {
    if (!chatInput.trim() || !coupleId || chatSending) return;
    const question = chatInput.trim();
    setChatInput('');
    setChatMessages((prev) => [...prev, { role: 'Couple', content: question }]);
    setChatSending(true);
    try {
      const res = await fetch(`${API_BASE}/couple/${coupleId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: question, language }),
      });
      if (res.ok) {
        const data = await res.json();
        setChatMessages((prev) => [...prev, { role: 'Astrologer', content: data.message }]);
      }
    } catch (err) {
      console.error('Couple chat failed:', err);
    } finally {
      setChatSending(false);
    }
  };

  const renderPartnerFormFields = (
    label: string,
    form: PartnerForm,
    setForm: (f: PartnerForm) => void
  ) => (
    <div className="flex-1 bg-white border border-slate-200 rounded-2xl p-5">
      <h3 className="text-sm font-semibold text-slate-700 mb-3">{label}</h3>
      <div className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Name</label>
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            placeholder="Full name"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Date of Birth</label>
          <input
            type="date"
            value={form.dob}
            onChange={(e) => setForm({ ...form, dob: e.target.value })}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Birth Time</label>
          <input
            type="time"
            value={form.birthTime}
            onChange={(e) => setForm({ ...form, birthTime: e.target.value })}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Birth Place</label>
          <input
            value={form.birthPlace}
            onChange={(e) => setForm({ ...form, birthPlace: e.target.value })}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            placeholder="e.g. Lucknow"
          />
        </div>
      </div>
    </div>
  );

  const VERDICT_BADGE_STYLES: Record<string, string> = {
  Strong: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  Favorable: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  'Mixed / Moderate': 'bg-amber-50 text-amber-700 border-amber-200',
  Challenged: 'bg-rose-50 text-rose-700 border-rose-200',
  Weak: 'bg-rose-50 text-rose-700 border-rose-200',
};

const renderAssessmentRow = (label: string, a: PlanetAssessment | null) => {
  if (!a) return (
    <div className="flex justify-between text-xs">
      <span className="text-slate-400">{label}</span>
      <span className="text-slate-400">—</span>
    </div>
  );
  return (
    <div className="text-xs py-1.5 border-b border-slate-50 last:border-0">
      <div className="flex justify-between items-start gap-2">
        <span className="text-slate-400 shrink-0">{label}</span>
        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border shrink-0 ${VERDICT_BADGE_STYLES[a.verdict] || 'bg-slate-100 text-slate-500 border-slate-200'}`}>
          {a.verdict}
        </span>
      </div>
      <p className="text-slate-600 mt-1 leading-snug">{a.reason}</p>
      {a.lordships && a.lordships.length > 0 && (
        <p className="text-slate-400 text-[10px] mt-0.5">Rules house{a.lordships.length > 1 ? 's' : ''} {a.lordships.join(', ')}</p>
      )}
    </div>
  );
};

const renderPartnerFactsCard = (name: string, report: PartnerReport) => (
  <div className="bg-white border border-slate-200 rounded-2xl p-5">
    <div className="flex items-center justify-between mb-3">
      <h3 className="text-sm font-bold text-slate-800">{name}</h3>
      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border capitalize ${VERDICT_STYLES[report.verdict] || VERDICT_STYLES.neutral}`}>
        {report.verdict}
      </span>
    </div>
    <div className="space-y-1 mb-2">
      <div className="flex justify-between text-xs">
        <span className="text-slate-400">5th House Sign</span>
        <span className="font-medium text-slate-800">{report.facts.sign || '—'}</span>
      </div>
      <div className="flex justify-between text-xs">
        <span className="text-slate-400">5th House Lord</span>
        <span className="font-medium text-slate-800">{report.facts.lord || '—'}</span>
      </div>
      <div className="flex justify-between text-xs">
        <span className="text-slate-400">Planets in 5th</span>
        <span className="font-medium text-slate-800">
          {report.facts.occupants.length ? report.facts.occupants.map((o) => o.name).join(', ') : 'None'}
        </span>
      </div>
      <div className="flex justify-between text-xs">
        <span className="text-slate-400">Current Dasha</span>
        <span className="font-medium text-slate-800">{report.current_dasha || '—'}</span>
      </div>
    </div>

    <div className="mt-3 pt-2 border-t border-slate-100">
      {renderAssessmentRow('5th Lord Strength', report.facts.lord_assessment)}
      {renderAssessmentRow('Jupiter (Child Significator)', report.facts.significator_assessment)}
    </div>

    {report.favorable_periods.length > 0 && (
      <div className="mt-3 pt-3 border-t border-slate-100">
        <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1.5">Favorable Upcoming Periods</p>
        {report.favorable_periods.slice(0, 3).map((p, i) => (
          <p key={i} className="text-xs text-slate-600">
            {p.mahadasha}/{p.antardasha}: {p.start.split(' ')[0]} – {p.end.split(' ')[0]}
          </p>
        ))}
      </div>
    )}
  </div>
);

  return (
    <div className="flex flex-col h-full bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between shrink-0">
        <button onClick={onBack} className="flex items-center gap-1.5 text-slate-500 hover:text-slate-800 text-sm font-medium transition">
          <ArrowLeft size={16} /> Dashboard
        </button>
        <div className="flex items-center gap-2.5">
          <div className="p-2 bg-rose-500 text-white rounded-xl shadow-sm"><Heart size={20} /></div>
          <h1 className="text-lg font-bold text-slate-800 leading-none">Couple Test</h1>
        </div>
        {step === 'dashboard' ? (
          <button onClick={handleReset} className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-700 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-lg transition">
            <RotateCcw size={12} /> New Test
          </button>
        ) : <div className="w-24" />}
      </header>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-5xl mx-auto space-y-6">

          {step === 'form' && (
            <>
              <p className="text-sm text-slate-500 text-center max-w-xl mx-auto">
                Enter both partners' birth details to generate a joint childbirth (Santan Yoga) analysis —
                each 5th house, its lord, Jupiter's placement, current Dasha, and the most likely favorable period.
              </p>
              <div className="flex flex-col md:flex-row gap-4">
                {renderPartnerFormFields('Partner 1', p1Form, setP1Form)}
                {renderPartnerFormFields('Partner 2', p2Form, setP2Form)}
              </div>
              {formError && <p className="text-sm text-rose-500 text-center">{formError}</p>}
              <div className="flex justify-center">
                <button
                  onClick={handleStartTest}
                  disabled={submitting}
                  className="flex items-center gap-2 rounded-xl bg-rose-500 hover:bg-rose-600 disabled:opacity-50 px-6 py-3 text-sm font-semibold text-white transition shadow-sm"
                >
                  {submitting ? <Loader2 size={16} className="animate-spin" /> : <Heart size={16} />}
                  Compare Kundlis
                </button>
              </div>
            </>
          )}

          {step === 'loading' && (
            <div className="flex flex-col items-center justify-center gap-4 py-16">
              {loadError ? (
                <>
                  <p className="text-sm text-rose-500 text-center max-w-sm">{loadError}</p>
                  <button onClick={retryLoading} className="flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-lg transition">
                    <RotateCcw size={12} /> Retry
                  </button>
                </>
              ) : (
                <>
                  <div className="w-8 h-8 border-2 border-slate-200 border-t-rose-500 rounded-full animate-spin" />
                  <p className="text-sm text-slate-500">Calculating both charts and Dasha periods...</p>
                  <div className="flex gap-6 text-xs text-slate-400">
                    <span>{p1?.status === 'ready' ? '✓' : '◉'} Partner 1</span>
                    <span>{p2?.status === 'ready' ? '✓' : '◉'} Partner 2</span>
                  </div>
                  <p className="text-[10px] text-slate-300">This can take up to a couple of minutes.</p>
                </>
              )}
            </div>
          )}

          {step === 'dashboard' && p1 && p2 && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <h2 className="text-sm font-semibold text-slate-700 mb-2 text-center">{p1.name}</h2>
                  {p1.planets && p1.ascendant_sign && (
                    <KundliChartToggle planets={p1.planets} ascendantSign={p1.ascendant_sign} language={language} sessionId={coupleId} />
                  )}
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-slate-700 mb-2 text-center">{p2.name}</h2>
                  {p2.planets && p2.ascendant_sign && (
                    <KundliChartToggle planets={p2.planets} ascendantSign={p2.ascendant_sign} language={language} sessionId={coupleId} />
                  )}
                </div>
              </div>

              {childbirth ? (
                <>
                  <div>
                    <h2 className="text-sm font-bold text-slate-800 mb-3">Childbirth (Santan Yoga) Factors</h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {renderPartnerFactsCard(childbirth.partner1_name, childbirth.partner1_report)}
                      {renderPartnerFactsCard(childbirth.partner2_name, childbirth.partner2_report)}
                    </div>
                  </div>
                  <div className="bg-white border border-slate-200 rounded-2xl p-5">
                   <h2 className="text-sm font-bold text-slate-800 mb-1">Known Real-World Outcome (optional)</h2>
                   <p className="text-xs text-slate-400 mb-3">
                      If you're testing a known case, tell the system what actually happened —
                      it will use this as ground truth instead of guessing from the chart alone.
                   </p>
                   <div className="flex gap-2">
                     <input
                         value={knownOutcome}
                         onChange={(e) => setKnownOutcome(e.target.value)}
                         placeholder="e.g. Married ~6 years, no child as of 2026"
                         className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
                     />
                     <button
                           onClick={handleSaveOutcome}
                           className="px-3 py-2 rounded-lg text-xs font-semibold bg-slate-900 text-white hover:bg-slate-800 transition shrink-0"
                     >
                           {outcomeSaved ? 'Saved ✓' : 'Save'}
                     </button>
                    </div>
                  </div>
                  <div className="bg-white border border-slate-200 rounded-2xl p-5">
                    <div className="flex items-center justify-between mb-3">
                      <h2 className="text-sm font-bold text-slate-800">Joint Couple Analysis</h2>
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border capitalize ${VERDICT_STYLES[childbirth.joint.joint_verdict] || VERDICT_STYLES.neutral}`}>
                        {childbirth.joint.joint_verdict}
                      </span>
                    </div>

                    {childbirth.joint.common_factors.length > 0 && (
                      <div className="mb-3">
                        <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1">Common Supporting Factors</p>
                        <ul className="text-xs text-slate-600 space-y-1 list-disc list-inside">
                          {childbirth.joint.common_factors.map((f, i) => <li key={i}>{f}</li>)}
                        </ul>
                      </div>
                    )}

                    {childbirth.joint.conflicting_factors.length > 0 && (
                      <div className="mb-3">
                        <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1">Conflicting Factors</p>
                        <ul className="text-xs text-slate-600 space-y-1 list-disc list-inside">
                          {childbirth.joint.conflicting_factors.map((f, i) => <li key={i}>{f}</li>)}
                        </ul>
                      </div>
                    )}

                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1">Most Likely Joint Window</p>
                      {childbirth.joint.overlapping_windows.length > 0 ? (
                        <p className="text-xs text-slate-700 font-medium">
                          {childbirth.joint.overlapping_windows[0].start} – {childbirth.joint.overlapping_windows[0].end}
                        </p>
                      ) : (
                        <p className="text-xs text-slate-400">No clearly overlapping favorable Dasha window was found — the chat below can explore individual timing further.</p>
                      )}
                      <p className="text-[10px] text-slate-300 mt-1">Only periods starting after today are considered as future predictions.</p>
                    </div>
                  </div>
                </>
              ) : (
                <p className="text-sm text-slate-400 text-center">Loading childbirth analysis...</p>
              )}

              <div className="bg-white border border-slate-200 rounded-2xl p-5">
                <h2 className="text-sm font-bold text-slate-800 mb-3">Ask About Your Childbirth Timing</h2>
                <div className="space-y-3 max-h-64 overflow-y-auto mb-3">
                  {chatMessages.length === 0 && (
                    <p className="text-xs text-slate-400">e.g. "Will we have a child, and when?"</p>
                  )}
                  {chatMessages.map((m, i) => (
                    <div key={i} className={`flex ${m.role === 'Couple' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[80%] rounded-xl px-3 py-2 text-xs ${m.role === 'Couple' ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700'}`}>
                        {m.content}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSendChat()}
                    placeholder="Will we have a child, and when?"
                    disabled={chatSending}
                    className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:opacity-50"
                  />
                  <button
                    onClick={handleSendChat}
                    disabled={chatSending || !chatInput.trim()}
                    className="p-2.5 bg-rose-500 hover:bg-rose-600 disabled:bg-slate-200 text-white rounded-lg transition shrink-0"
                  >
                    {chatSending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}