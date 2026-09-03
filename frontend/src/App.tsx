import { useState, useEffect, useRef, useCallback } from 'react';
import { ChatWindow } from './components/ChatWindow';
import { ChatInput } from './components/ChatInput';
import { ProfileCard } from './components/ProfileCard';
import { Sparkles, Database, CheckCircle, ArrowLeft, Download, Trash2, RotateCcw, Heart } from 'lucide-react';
import OnboardingForm from './components/OnboardingForm';
import KundliChartToggle from './components/KundliChartToggle';
import LifeDashboard from './components/LifeDashboard';
import EditDetailsModal from './components/EditDetailsModal';
import GoToChatCard from './components/GoToChatCard';
import WeeklyGuidance from './components/WeeklyGuidance';
import FaqStarter from './components/FaqStarter';
import ReasoningTrace from './components/ReasoningTrace';
import KundliReportButton from './components/KundliReportButton';
import CouplePage from './components/CouplePage';

interface Message { role: 'user' | 'assistant' | 'system'; content: string; timestamp?: string; }
interface IngestStatus { indexing_completed: boolean; total_chunks: number; loading: boolean; }

const API_BASE = ((import.meta as ImportMeta & { env?: { VITE_API_BASE?: string } }).env?.VITE_API_BASE) || '/api';

const GREETINGS: Record<string, (name: string) => string> = {
  English: (name) => `Hey ${name}!`,
  Hindi: (name) => `नमस्ते ${name}!`,
  Hinglish: (name) => `Hey ${name}!`,
};

// Chart calculation genuinely can take 1-3 minutes (Kundli lambda retries
// + Dasha lambda retries stacked). Poll status (cheap DB read) rather than
// re-triggering the fetch, and keep polling for up to ~4 minutes before
// calling it stuck — matching the backend's own stale-pending window.
const STATUS_POLL_INTERVAL_MS = 4000;
const STATUS_POLL_MAX_ATTEMPTS = 60; // 60 * 4s = 240s

type ChartStatus = 'idle' | 'loading' | 'ready' | 'failed';
type ViewMode = 'dashboard' | 'chat' | 'couple';

function App() {
  const [sessionId, setSessionId] = useState<string>('');
  const [onboarded, setOnboarded] = useState<boolean>(false);
  const [checkingProfile, setCheckingProfile] = useState<boolean>(true);
  const [view, setView] = useState<ViewMode>('dashboard');

  const [name, setName] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [dob, setDob] = useState<string | null>(null);
  const [birthTime, setBirthTime] = useState<string | null>(null);
  const [birthPlace, setBirthPlace] = useState<string | null>(null);
  const [language, setLanguage] = useState<string>('Hinglish');

  const [isTyping, setIsTyping] = useState<boolean>(false);
  const [isResetting, setIsResetting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [kundliPlanets, setKundliPlanets] = useState<any[] | null>(null);
  const [ascendantSign, setAscendantSign] = useState<string | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [traceRefreshKey, setTraceRefreshKey] = useState(0);
  const [ingestStatus, setIngestStatus] = useState<IngestStatus>({ indexing_completed: false, total_chunks: 0, loading: true });

  // --- Chart loading state ---
  const [chartStatus, setChartStatus] = useState<ChartStatus>('idle');
  const [chartError, setChartError] = useState<string | null>(null);
  const chartPollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chartPollAttempt = useRef(0);
  const chartPollingFor = useRef<string | null>(null);

  useEffect(() => {
    let sid = localStorage.getItem('call-astro_session_id');
    if (!sid) {
      sid = 'session_' + Math.random().toString(36).substring(2, 15);
      localStorage.setItem('call-astro_session_id', sid);
    }
    setSessionId(sid);
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    const fetchSessionData = async () => {
      try {
        const profileRes = await fetch(`${API_BASE}/session/${sessionId}`);
        if (profileRes.ok) {
          const profile = await profileRes.json();
          setName(profile.name);
          setDob(profile.dob);
          setBirthTime(profile.birth_time);
          setBirthPlace(profile.birth_place);
          setLanguage(profile.language);
          if (profile.dob && profile.birth_time && profile.birth_place) setOnboarded(true);
        }
        const historyRes = await fetch(`${API_BASE}/chat/history/${sessionId}`);
        if (historyRes.ok) {
          const history = await historyRes.json();
          setMessages(history.messages);
        }
      } catch (err) {
        console.error('Error fetching session data:', err);
        setError('Could not connect to the backend server. Please verify it is running.');
      } finally {
        setCheckingProfile(false);
      }
    };
    fetchSessionData();
    checkIngestStatus();
  }, [sessionId]);

  // ------------------------------------------------------------------
  // CHART LOADING — polls the lightweight /kundli-status endpoint
  // instead of guessing off a fixed timer. Distinguishes "still working"
  // from "actually failed" using the real backend status + error message.
  // ------------------------------------------------------------------
  const stopChartPolling = useCallback(() => {
    if (chartPollTimer.current) {
      clearTimeout(chartPollTimer.current);
      chartPollTimer.current = null;
    }
  }, []);

  const fetchChartData = useCallback(async (sid: string): Promise<boolean> => {
    try {
      const res = await fetch(`${API_BASE}/session/${sid}/kundli-chart`);
      if (!res.ok) return false;
      const data = await res.json();
      if (data.available && data.planets && data.ascendant_sign) {
        setKundliPlanets(data.planets);
        setAscendantSign(data.ascendant_sign);
        return true;
      }
      return false;
    } catch (err) {
      console.error('Failed to load kundli chart:', err);
      return false;
    }
  }, []);

  const pollChartStatus = useCallback((sid: string) => {
    stopChartPolling();
    chartPollingFor.current = sid;
    chartPollAttempt.current = 0;
    setChartStatus('loading');
    setChartError(null);

    const tick = async () => {
      if (chartPollingFor.current !== sid) return;

      try {
        const res = await fetch(`${API_BASE}/session/${sid}/kundli-status`);
        if (res.ok) {
          const data = await res.json();
          if (chartPollingFor.current !== sid) return;

          if (data.status === 'ready' && data.has_chart) {
            const ready = await fetchChartData(sid);
            if (chartPollingFor.current !== sid) return;
            if (ready) {
              setChartStatus('ready');
              return;
            }
            // status says ready but chart payload isn't parseable yet —
            // treat as a transient race and keep polling briefly.
          } else if (data.status === 'failed') {
            setChartStatus('failed');
            setChartError(data.error || 'Chart calculation failed. Please retry.');
            return;
          }
          // status === 'pending' or 'idle' -> keep polling
        }
      } catch (err) {
        console.error('Chart status poll failed:', err);
      }

      const attempt = chartPollAttempt.current;
      if (attempt >= STATUS_POLL_MAX_ATTEMPTS) {
        setChartStatus('failed');
        setChartError('This is taking longer than expected. Please retry.');
        return;
      }
      chartPollAttempt.current += 1;
      chartPollTimer.current = setTimeout(tick, STATUS_POLL_INTERVAL_MS);
    };

    tick();
  }, [fetchChartData, stopChartPolling]);

  const triggerKundliFetch = useCallback(async (sid: string) => {
    try {
      const res = await fetch(`${API_BASE}/session/${sid}/recalculate-kundli`, { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setChartStatus('failed');
        setChartError(body?.detail || 'Could not start chart calculation.');
        return;
      }
      // Backend returns immediately with status "pending" — polling picks up the result.
    } catch (err) {
      console.error('Failed to trigger kundli fetch:', err);
      setChartStatus('failed');
      setChartError('Could not reach the backend to start chart calculation.');
    }
  }, []);

  useEffect(() => {
    if (!sessionId || !onboarded) return;
    if (kundliPlanets && ascendantSign) return;
    if (chartStatus === 'loading' || chartStatus === 'ready') return;

    triggerKundliFetch(sessionId);
    pollChartStatus(sessionId);

    return () => stopChartPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, onboarded]);

  const retryChartLoad = () => {
    if (!sessionId) return;
    triggerKundliFetch(sessionId);
    pollChartStatus(sessionId);
  };

  const checkIngestStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/ingest/status`);
      if (res.ok) {
        const data = await res.json();
        setIngestStatus({ indexing_completed: data.indexing_completed, total_chunks: data.total_chunks, loading: false });
      }
    } catch (err) {
      console.error('Error checking ingest status:', err);
      setIngestStatus(prev => ({ ...prev, loading: false }));
    }
  };

  const handleSendMessage = async (text: string) => {
    const userMsg: Message = { role: 'user', content: text, timestamp: new Date().toISOString() };
    setMessages(prev => [...prev, userMsg]);
    setIsTyping(true);
    setError(null);
    setSuggestions([]);

    let assistantIndex = -1;
    setMessages(prev => {
      assistantIndex = prev.length;
      return [...prev, { role: 'assistant', content: '', timestamp: new Date().toISOString() }];
    });

    try {
      const response = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: text })
      });
      if (!response.ok || !response.body) throw new Error('Server error');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let accumulatedText = '';
      setIsTyping(false);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          if (!part.startsWith('data: ')) continue;
          let event: any;
          try { event = JSON.parse(part.slice(6)); } catch { continue; }

          if (event.type === 'chunk') {
            accumulatedText += event.text;
            setMessages(prev => {
              const updated = [...prev];
              updated[assistantIndex] = { ...updated[assistantIndex], content: accumulatedText };
              return updated;
            });
          } else if (event.type === 'done') {
            setDob(event.dob);
            setBirthTime(event.birth_time);
            setBirthPlace(event.birth_place);
            setLanguage(event.language);
            if (event.suggestions && Array.isArray(event.suggestions)) {
              setSuggestions(event.suggestions);
            }
            setTraceRefreshKey(prev => prev + 1);
          }
        }
      }
    } catch (err: any) {
      console.error('Failed to send message:', err);
      setError(err.message || 'Something went wrong. Is Ollama running?');
    } finally {
      setIsTyping(false);
    }
  };

  const handleResetSession = async () => {
    if (!sessionId) return;
    setIsResetting(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}`, { method: 'DELETE' });
      if (res.ok) {
        stopChartPolling();
        chartPollingFor.current = null;
        const newSid = 'session_' + Math.random().toString(36).substring(2, 15);
        localStorage.setItem('call-astro_session_id', newSid);
        setSessionId(newSid);
        setMessages([]);
        setName(null);
        setDob(null);
        setBirthTime(null);
        setBirthPlace(null);
        setLanguage('Hinglish');
        setOnboarded(false);
        setView('dashboard');
        setKundliPlanets(null);
        setAscendantSign(null);
        setChartStatus('idle');
        setChartError(null);
      }
    } catch (err) {
      console.error('Reset failed:', err);
      setError('Failed to reset session data.');
    } finally {
      setIsResetting(false);
    }
  };

  const handleOnboardingComplete = (profile: { dob: string; birth_time: string; birth_place: string; language: string; name: string }) => {
    setName(profile.name);
    setDob(profile.dob);
    setBirthTime(profile.birth_time);
    setBirthPlace(profile.birth_place);
    setLanguage(profile.language);
    setOnboarded(true);
    setView('dashboard');

    if (sessionId) {
      triggerKundliFetch(sessionId);
      pollChartStatus(sessionId);
    }
  };

  if (checkingProfile) {
    return <div className="flex h-screen items-center justify-center text-slate-400">Loading...</div>;
  }

  if (!onboarded) {
    return <OnboardingForm sessionId={sessionId} onComplete={handleOnboardingComplete} />;
  }

  const exportChat = () => {
    if (messages.length === 0) return;
    const textData = messages.map(msg => {
      const role = msg.role === 'user' ? 'You' : 'Astrologer';
      return `[${msg.timestamp || new Date().toISOString()}] ${role}:\n${msg.content}\n`;
    }).join('\n');
    const blob = new Blob([textData], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'Call-Astro_Chat_Export.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const clearChat = async () => {
    if (!confirm('Are you sure you want to clear your chat history?')) return;
    try {
      const res = await fetch(`${API_BASE}/chat/history/${sessionId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setMessages([]);
      } else {
        setError('Failed to clear chat history');
      }
    } catch (err) {
      setError('Network error clearing chat history');
    }
  };

  const renderChartPanel = () => {
    if (kundliPlanets && ascendantSign) {
      return <KundliChartToggle planets={kundliPlanets} ascendantSign={ascendantSign} language={language} sessionId={sessionId} />;
    }

    if (chartStatus === 'failed') {
      return (
        <div className="w-full bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex flex-col items-center justify-center gap-3 text-sm text-slate-400 h-full text-center">
          <span>{chartError || "Couldn't load your chart right now."}</span>
          <button
            onClick={retryChartLoad}
            className="flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-slate-800 bg-slate-50 hover:bg-slate-100 px-3 py-1.5 rounded-lg transition"
          >
            <RotateCcw size={12} /> Retry
          </button>
        </div>
      );
    }

    return (
      <div className="w-full bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex flex-col items-center justify-center gap-2 text-sm text-slate-400 h-full">
        <div className="w-5 h-5 border-2 border-slate-300 border-t-amber-500 rounded-full animate-spin" />
        <span>Preparing your chart...</span>
        <span className="text-[10px] text-slate-300">This can take up to a couple of minutes.</span>
      </div>
    );
  };

  // ---------------- COUPLE TEST VIEW ----------------
  if (view === 'couple') {
    return <CouplePage language={language} onBack={() => setView('dashboard')} />;
  }

  // ---------------- DASHBOARD VIEW ----------------
  if (view === 'dashboard') {
    const greetingFn = GREETINGS[language] || GREETINGS.Hinglish;
    const greeting = name ? greetingFn(name) : '';

    return (
      <div className="flex flex-col h-full bg-slate-50">
        <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-amber-500 text-white rounded-xl shadow-sm"><Sparkles size={20} /></div>
            <div>
              <h1 className="text-lg font-bold text-slate-800 leading-none">Call-Astro</h1>
              <p className="text-[10px] text-slate-400 font-medium mt-0.5">{greeting || 'Your Dashboard'}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setView('couple')}
              className="flex items-center gap-1.5 text-xs font-semibold text-white bg-rose-500 hover:bg-rose-600 px-3 py-2 rounded-lg shadow-sm transition"
            >
              <Heart size={14} /> Couple Test
            </button>
            {kundliPlanets && ascendantSign && (
              <KundliReportButton sessionId={sessionId} language={language} name={name} />
            )}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="max-w-6xl mx-auto space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch">
              <ProfileCard
                dob={dob} birthTime={birthTime} birthPlace={birthPlace} language={language}
                onReset={handleResetSession} onEdit={() => setShowEditModal(true)} isResetting={isResetting}
              />
              {renderChartPanel()}
              <LifeDashboard sessionId={sessionId} language={language} />
            </div>

            <GoToChatCard language={language} onGoToChat={() => setView('chat')} />
          </div>
        </div>

        {showEditModal && (
          <EditDetailsModal
            sessionId={sessionId} currentName={name} currentDob={dob}
            currentBirthTime={birthTime} currentBirthPlace={birthPlace} currentLanguage={language}
            onClose={() => setShowEditModal(false)}
            onSaved={async (profile) => {
              setName(profile.name);
              setDob(profile.dob);
              setBirthTime(profile.birth_time);
              setBirthPlace(profile.birth_place);
              setLanguage(profile.language);
              setKundliPlanets(null);
              setAscendantSign(null);
              setChartStatus('idle');
              setChartError(null);
              const historyRes = await fetch(`${API_BASE}/chat/history/${sessionId}`);
              if (historyRes.ok) {
                const history = await historyRes.json();
                setMessages(history.messages);
              }
              pollChartStatus(sessionId);
            }}
          />
        )}
      </div>
    );
  }

  // ---------------- CHAT VIEW ----------------
  return (
    <div className="flex flex-col h-full bg-slate-50">
      {!ingestStatus.loading && !ingestStatus.indexing_completed && (
        <div className="bg-blue-50 border-b border-blue-200 px-4 py-2 text-sm text-blue-700 flex items-center gap-2">
          <Database size={16} className="text-blue-600 shrink-0 animate-pulse" />
          <span><strong>Knowledge base indexing...</strong> Automatic indexing completed on server startup.</span>
        </div>
      )}

      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between shrink-0">
        <button onClick={() => setView('dashboard')} className="flex items-center gap-1.5 text-slate-500 hover:text-slate-800 text-sm font-medium transition">
          <ArrowLeft size={16} /> Dashboard
        </button>
        <div className="flex items-center gap-2.5">
          <div className="p-2 bg-amber-500 text-white rounded-xl shadow-sm"><Sparkles size={20} /></div>
          <h1 className="text-lg font-bold text-slate-800 leading-none">Call-Astro</h1>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={exportChat} className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition" title="Export Chat">
            <Download size={18} />
          </button>
          <button onClick={clearChat} className="p-1.5 text-rose-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition" title="Clear Chat">
            <Trash2 size={18} />
          </button>
          <div className="hidden sm:flex items-center gap-2 border-l border-slate-200 pl-2 ml-1">
            {ingestStatus.indexing_completed ? (
              <div className="flex items-center gap-1 text-emerald-600 bg-emerald-50 px-2.5 py-1 rounded-full text-xs font-medium border border-emerald-100">
                <CheckCircle size={12} /><span>RAG Active: {ingestStatus.total_chunks} Chunks</span>
              </div>
            ) : (
              <div className="flex items-center gap-1 text-slate-500 bg-slate-100 px-2.5 py-1 rounded-full text-xs font-medium border border-slate-200">
                <Database size={12} /><span>RAG: Initializing</span>
              </div>
            )}
          </div>
        </div>
      </header>

      {error && (
        <div className="bg-rose-50 border-b border-rose-200 px-6 py-3 text-sm text-rose-700 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-rose-400 hover:text-rose-600 font-semibold text-xs ml-4">Dismiss</button>
        </div>
      )}

      <div className="flex-1 flex overflow-hidden">
        <main className="flex-1 flex flex-col min-w-0 bg-slate-50">
          <ChatWindow messages={messages} isTyping={isTyping} language={language} suggestions={suggestions} onSuggestionSelect={handleSendMessage} />
          <FaqStarter onSelect={handleSendMessage} disabled={isTyping} language={language} />
          <ChatInput onSendMessage={handleSendMessage} disabled={isTyping} language={language} />
        </main>
        <aside className="hidden lg:block w-72 border-l border-slate-200 bg-slate-50 p-4 overflow-y-auto shrink-0">
          <WeeklyGuidance sessionId={sessionId} language={language} />
          <ReasoningTrace sessionId={sessionId} key={traceRefreshKey} />
        </aside>
      </div>
    </div>
  );
}

export default App;