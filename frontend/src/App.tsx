import { useState, useEffect, useRef, useCallback } from 'react';
import { ChatWindow } from './components/ChatWindow';
import { ChatInput } from './components/ChatInput';
import { ProfileCard } from './components/ProfileCard';
import { Sparkles, Database, CheckCircle, ArrowLeft, Download, Trash2, RotateCcw } from 'lucide-react';
import OnboardingForm from './components/OnboardingForm';
import KundliChartToggle from './components/KundliChartToggle';
import LifeDashboard from './components/LifeDashboard';
import EditDetailsModal from './components/EditDetailsModal';
import GoToChatCard from './components/GoToChatCard';
import WeeklyGuidance from './components/WeeklyGuidance';
import FaqStarter from './components/FaqStarter';
import ReasoningTrace from './components/ReasoningTrace';

interface Message { role: 'user' | 'assistant' | 'system'; content: string; timestamp?: string; }
interface IngestStatus { indexing_completed: boolean; total_chunks: number; loading: boolean; }

const API_BASE = ((import.meta as ImportMeta & { env?: { VITE_API_BASE?: string } }).env?.VITE_API_BASE) || '/api';

const GREETINGS: Record<string, (name: string) => string> = {
  English: (name) => `Hey ${name}!`,
  Hindi: (name) => `नमस्ते ${name}!`,
  Hinglish: (name) => `Hey ${name}!`,
};

// Chart-loading tuning: poll fast at first (kundli fetch is usually a
// couple seconds), back off, and give up with a manual retry after ~90s
// total instead of spinning forever.
const CHART_POLL_INTERVALS_MS = [1500, 1500, 2000, 2000, 3000, 3000, 5000, 5000, 5000, 5000, 8000, 8000];

function App() {
  const [sessionId, setSessionId] = useState<string>('');
  const [onboarded, setOnboarded] = useState<boolean>(false);
  const [checkingProfile, setCheckingProfile] = useState<boolean>(true);
  const [view, setView] = useState<'dashboard' | 'chat'>('dashboard');

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
  const [chartStatus, setChartStatus] = useState<'idle' | 'loading' | 'ready' | 'failed'>('idle');
  const chartPollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chartPollAttempt = useRef(0);
  const chartPollingFor = useRef<string | null>(null); // guards against stale timers after session reset

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
  // CHART LOADING — replaces the old "fetch once on mount / messages
  // change" effect. Two entry points feed into the same poll loop:
  //   1. Onboarding just completed -> we kick off a backend fetch AND
  //      start polling for the result.
  //   2. Dashboard mounts with an already-onboarded session that has no
  //      chart yet (e.g. user closed the tab before it finished last
  //      time) -> we also kick off a fetch and start polling.
  // The backend call (recalculate-kundli) is idempotent and safe to
  // fire even if a fetch is already in flight elsewhere.
  // ------------------------------------------------------------------
  const stopChartPolling = useCallback(() => {
    if (chartPollTimer.current) {
      clearTimeout(chartPollTimer.current);
      chartPollTimer.current = null;
    }
  }, []);

  const fetchChartOnce = useCallback(async (sid: string): Promise<boolean> => {
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

  const pollForChart = useCallback((sid: string) => {
    stopChartPolling();
    chartPollingFor.current = sid;
    chartPollAttempt.current = 0;
    setChartStatus('loading');

    const tick = async () => {
      if (chartPollingFor.current !== sid) return; // session changed under us, abandon
      const ready = await fetchChartOnce(sid);
      if (chartPollingFor.current !== sid) return;

      if (ready) {
        setChartStatus('ready');
        return;
      }

      const idx = chartPollAttempt.current;
      if (idx >= CHART_POLL_INTERVALS_MS.length) {
        setChartStatus('failed');
        return;
      }
      const delay = CHART_POLL_INTERVALS_MS[idx];
      chartPollAttempt.current += 1;
      chartPollTimer.current = setTimeout(tick, delay);
    };

    tick();
  }, [fetchChartOnce, stopChartPolling]);

  // Kick the backend to actually compute the chart (fire-and-forget —
  // the poll loop above is what picks up the result once it's ready).
  const triggerKundliFetch = useCallback((sid: string) => {
    fetch(`${API_BASE}/session/${sid}/recalculate-kundli`, { method: 'POST' }).catch((err) => {
      console.error('Failed to trigger kundli fetch:', err);
    });
  }, []);

  // Entry point 2: dashboard mounts / session becomes known and profile
  // is complete but we don't have a chart yet — start the same flow.
  useEffect(() => {
    if (!sessionId || !onboarded) return;
    if (kundliPlanets && ascendantSign) return; // already have it
    if (chartStatus === 'loading' || chartStatus === 'ready') return;

    triggerKundliFetch(sessionId);
    pollForChart(sessionId);

    return () => stopChartPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, onboarded]);

  // Re-check the chart right after a NEW assistant message lands too —
  // cheap safety net, and it's a single fetch (not a full poll restart)
  // since by then the backend has almost certainly already computed it.
  useEffect(() => {
    if (!sessionId || chartStatus === 'ready') return;
    if (messages.length === 0) return;
    fetchChartOnce(sessionId).then((ready) => {
      if (ready) {
        stopChartPolling();
        setChartStatus('ready');
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.length]);

  const retryChartLoad = () => {
    if (!sessionId) return;
    triggerKundliFetch(sessionId);
    pollForChart(sessionId);
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

    // Entry point 1 — fire the fetch immediately instead of waiting for
    // the first chat message. The dashboard-mount effect below will also
    // start polling once `onboarded` flips true.
    if (sessionId) {
      triggerKundliFetch(sessionId);
      pollForChart(sessionId);
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

  // --- Chart panel renderer (replaces the old ternary inline in JSX) ---
  const renderChartPanel = () => {
    if (kundliPlanets && ascendantSign) {
      return <KundliChartToggle planets={kundliPlanets} ascendantSign={ascendantSign} language={language} sessionId={sessionId} />;
    }

    if (chartStatus === 'failed') {
      return (
        <div className="w-full bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex flex-col items-center justify-center gap-3 text-sm text-slate-400 h-full">
          <span>Couldn't load your chart right now.</span>
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
      </div>
    );
  };

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
              setChartStatus('loading');
              const historyRes = await fetch(`${API_BASE}/chat/history/${sessionId}`);
              if (historyRes.ok) {
                const history = await historyRes.json();
                setMessages(history.messages);
              }
              // EditDetailsModal already calls recalculate-kundli itself —
              // we just need to start polling for the result here.
              pollForChart(sessionId);
            }}
          />
        )}
      </div>
    );
  }

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