import { useEffect, useRef, useState } from 'react';
import { FileText, Loader2, CheckCircle2, XCircle, X } from 'lucide-react';

const API_BASE =
  ((import.meta as ImportMeta & { env?: { VITE_API_BASE?: string } }).env?.VITE_API_BASE) || '/api';

interface KundliReportButtonProps {
  sessionId: string;
  language: string;
  name: string | null;
}

interface ProgressStep {
  key: string;
  label: string;
  done: boolean;
}

type Phase = 'idle' | 'pending' | 'generating' | 'ready' | 'failed';

const POLL_INTERVAL_MS = 1500;
const POLL_MAX_ATTEMPTS = 120; // 3 minutes

const LABELS: Record<string, {
  button: string;
  modalTitle: string;
  modalSubtitle: string;
  readyTitle: string;
  readySubtitle: string;
  downloadCta: string;
  failedTitle: string;
  retry: string;
  close: string;
  error: string;
}> = {
  English: {
    button: 'Download Kundli PDF',
    modalTitle: 'Preparing Your Kundli',
    modalSubtitle: 'Your personalized report is being prepared using your birth chart.',
    readyTitle: 'Kundli Ready',
    readySubtitle: 'Your personalized Kundli report has been generated successfully.',
    downloadCta: 'Download PDF',
    failedTitle: "Couldn't generate the report",
    retry: 'Retry',
    close: 'Close',
    error: "Couldn't generate the report. Please try again.",
  },
  Hindi: {
    button: 'कुंडली PDF डाउनलोड करें',
    modalTitle: 'आपकी कुंडली तैयार की जा रही है',
    modalSubtitle: 'आपकी जन्म कुंडली के आधार पर व्यक्तिगत रिपोर्ट तैयार हो रही है।',
    readyTitle: 'कुंडली तैयार है',
    readySubtitle: 'आपकी व्यक्तिगत कुंडली रिपोर्ट सफलतापूर्वक तैयार हो गई है।',
    downloadCta: 'PDF डाउनलोड करें',
    failedTitle: 'रिपोर्ट नहीं बन सकी',
    retry: 'दोबारा कोशिश करें',
    close: 'बंद करें',
    error: 'रिपोर्ट नहीं बन सकी। कृपया दोबारा प्रयास करें।',
  },
  Hinglish: {
    button: 'Kundli PDF Download Karein',
    modalTitle: 'Aapki Kundli Taiyaar Ho Rahi Hai',
    modalSubtitle: 'Aapke birth chart ke aadhar par personalized report taiyaar ho rahi hai.',
    readyTitle: 'Kundli Ready Hai',
    readySubtitle: 'Aapki personalized Kundli report successfully taiyaar ho gayi hai.',
    downloadCta: 'PDF Download Karein',
    failedTitle: 'Report nahi ban saki',
    retry: 'Dobara Koshish Karein',
    close: 'Band Karein',
    error: 'Report nahi ban saki. Kripya dobara koshish karein.',
  },
};

export default function KundliReportButton({ sessionId, language, name }: KundliReportButtonProps) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [progress, setProgress] = useState<ProgressStep[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);

  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollAttempt = useRef(0);
  const pollingFor = useRef<string | null>(null);

  const t = LABELS[language] || LABELS.Hinglish;

  const stopPolling = () => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  };

  useEffect(() => () => stopPolling(), []);

  const pollStatus = (sid: string) => {
    stopPolling();
    pollingFor.current = sid;
    pollAttempt.current = 0;

    const tick = async () => {
      if (pollingFor.current !== sid) return;
      try {
        const res = await fetch(`${API_BASE}/session/${sid}/kundli-report/status`);
        if (res.ok) {
          const data = await res.json();
          if (pollingFor.current !== sid) return;

          setProgress(data.progress || []);

          if (data.status === 'ready' && data.ready) {
            setPhase('ready');
            return;
          }
          if (data.status === 'failed') {
            setPhase('failed');
            setError(data.error || t.error);
            return;
          }
          setPhase(data.status === 'generating' ? 'generating' : 'pending');
        }
      } catch (err) {
        console.error('Report status poll failed:', err);
      }

      if (pollAttempt.current >= POLL_MAX_ATTEMPTS) {
        setPhase('failed');
        setError('This is taking longer than expected. Please retry.');
        return;
      }
      pollAttempt.current += 1;
      pollTimer.current = setTimeout(tick, POLL_INTERVAL_MS);
    };

    tick();
  };

  const startGeneration = async () => {
    setShowModal(true);
    setError(null);
    setPhase('pending');
    setProgress([]);

    try {
      const res = await fetch(
        `${API_BASE}/session/${sessionId}/kundli-report/generate?language=${encodeURIComponent(language)}`,
        { method: 'POST' }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || t.error);
      }
      pollStatus(sessionId);
    } catch (err: any) {
      setPhase('failed');
      setError(err.message || t.error);
    }
  };

  const handleDownload = async () => {
    try {
      const res = await fetch(
        `${API_BASE}/session/${sessionId}/kundli-report/download?language=${encodeURIComponent(language)}`
      );
      if (!res.ok) throw new Error('Failed to download report');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(name || 'Kundli').replace(/\s+/g, '_')}_Kundli_${language}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Report download failed:', err);
      setError(t.error);
      setPhase('failed');
    }
  };

  const closeModal = () => {
    stopPolling();
    pollingFor.current = null;
    setShowModal(false);
  };

  return (
    <div className="flex flex-col items-end">
      <button
        onClick={startGeneration}
        disabled={phase === 'pending' || phase === 'generating'}
        className="flex items-center gap-1.5 text-xs font-semibold text-white bg-amber-500 hover:bg-amber-600 disabled:opacity-60 px-3 py-2 rounded-lg shadow-sm transition"
      >
        {phase === 'pending' || phase === 'generating' ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <FileText size={14} />
        )}
        {t.button}
      </button>

      {showModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 px-4">
          <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-lg relative">
            {(phase === 'ready' || phase === 'failed') && (
              <button
                onClick={closeModal}
                className="absolute top-4 right-4 text-slate-400 hover:text-slate-600"
              >
                <X size={18} />
              </button>
            )}

            {(phase === 'pending' || phase === 'generating') && (
              <>
                <div className="flex flex-col items-center text-center mb-5">
                  <div className="w-10 h-10 border-2 border-slate-200 border-t-amber-500 rounded-full animate-spin mb-3" />
                  <h2 className="text-base font-bold text-slate-800">{t.modalTitle}</h2>
                  <p className="text-xs text-slate-400 mt-1">{t.modalSubtitle}</p>
                </div>
                <div className="space-y-2.5">
                  {progress.map((step) => (
                    <div key={step.key} className="flex items-center gap-2.5 text-sm">
                      {step.done ? (
                        <CheckCircle2 size={16} className="text-emerald-500 shrink-0" />
                      ) : (
                        <Loader2 size={16} className="text-amber-500 animate-spin shrink-0" />
                      )}
                      <span className={step.done ? 'text-slate-700' : 'text-slate-400'}>
                        {step.label}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}

            {phase === 'ready' && (
              <div className="flex flex-col items-center text-center">
                <CheckCircle2 size={40} className="text-emerald-500 mb-3" />
                <h2 className="text-base font-bold text-slate-800">{t.readyTitle}</h2>
                <p className="text-xs text-slate-400 mt-1 mb-5">{t.readySubtitle}</p>
                <button
                  onClick={handleDownload}
                  className="w-full flex items-center justify-center gap-2 rounded-xl bg-amber-500 hover:bg-amber-600 py-2.5 text-sm font-semibold text-white transition"
                >
                  <FileText size={16} />
                  {t.downloadCta}
                </button>
              </div>
            )}

            {phase === 'failed' && (
              <div className="flex flex-col items-center text-center">
                <XCircle size={40} className="text-rose-500 mb-3" />
                <h2 className="text-base font-bold text-slate-800">{t.failedTitle}</h2>
                <p className="text-xs text-slate-400 mt-1 mb-5">{error || t.error}</p>
                <div className="flex gap-2 w-full">
                  <button
                    onClick={closeModal}
                    className="flex-1 rounded-xl border border-slate-200 py-2.5 text-sm font-medium text-slate-600"
                  >
                    {t.close}
                  </button>
                  <button
                    onClick={startGeneration}
                    className="flex-1 rounded-xl bg-amber-500 hover:bg-amber-600 py-2.5 text-sm font-semibold text-white transition"
                  >
                    {t.retry}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}