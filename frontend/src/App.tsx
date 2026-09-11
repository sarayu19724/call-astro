
import { useCallback, useEffect, useRef, useState } from 'react';
import { ChatWindow } from './components/ChatWindow';
import { ChatInput } from './components/ChatInput';
import { ProfileCard } from './components/ProfileCard';
import { Sparkles, Database, CheckCircle, ArrowLeft, Download, Trash2, Globe2, Compass, RotateCcw, Heart, CalendarDays } from 'lucide-react';
import OnboardingForm from './components/OnboardingForm';
import KundliChartToggle from './components/KundliChartToggle';
import LifeDashboard from './components/LifeDashboard';
import EditDetailsModal from './components/EditDetailsModal';
import AddProfileModal from './components/AddProfileModal';
import ProfileSwitcher, { Profile } from './components/ProfileSwitcher';
import TransitOverlayModal from './components/TransitOverlayModal';
import GoToChatCard from './components/GoToChatCard';
import WeeklyGuidance from './components/WeeklyGuidance';
import FaqStarter from './components/FaqStarter';
import ReasoningTrace from './components/ReasoningTrace';
import KundliReportButton from './components/KundliReportButton';
import CouplePage from './components/CouplePage';
import AstrologyCalendar from './components/AstrologyCalendar';
import { API_BASE } from './api';

interface Message { role: 'user' | 'assistant' | 'system'; content: string; timestamp?: string; }
interface IngestStatus { indexing_completed: boolean; total_chunks: number; loading: boolean; }

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

function App() {
  const [sessionId, setSessionId] = useState<string>('');
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [onboarded, setOnboarded] = useState<boolean>(false);
  const [checkingProfile, setCheckingProfile] = useState<boolean>(true);
  const [view, setView] = useState<'dashboard' | 'chat' | 'couple' | 'calendar'>('dashboard');

  const [name, setName] = useState<string | null>(null);
  const [relation, setRelation] = useState<string>('Self');
  const [messages, setMessages] = useState<Message[]>([]);
  const [dob, setDob] = useState<string | null>(null);
  const [birthTime, setBirthTime] = useState<string | null>(null);
  const [birthPlace, setBirthPlace] = useState<string | null>(null);
  const [language, setLanguage] = useState<string>('English');

  const [isTyping, setIsTyping] = useState<boolean>(false);
  const [isResetting, setIsResetting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [kundliPlanets, setKundliPlanets] = useState<any[] | null>(null);
  const [ascendantSign, setAscendantSign] = useState<string | null>(null);
  const [profileToEdit, setProfileToEdit] = useState<Profile | null>(null);
  const [showAddProfileModal, setShowAddProfileModal] = useState(false);
  const [showTransitModal, setShowTransitModal] = useState(false);
  const [traceRefreshKey, setTraceRefreshKey] = useState(0);
  const [ingestStatus, setIngestStatus] = useState<IngestStatus>({ indexing_completed: false, total_chunks: 0, loading: true });

  // --- Chart loading state ---
  const [chartStatus, setChartStatus] = useState<ChartStatus>('idle');
  const [chartError, setChartError] = useState<string | null>(null);
  const chartPollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chartPollAttempt = useRef(0);
  const chartPollingFor = useRef<string | null>(null);

  // 1. Initial boot: fetch all profiles from backend & initialize active session
  useEffect(() => {
    const initApp = async () => {
      let savedProfiles: Profile[] = [];
      const savedProfilesStr = localStorage.getItem('call-astro_profiles');
      if (savedProfilesStr) {
        try { savedProfiles = JSON.parse(savedProfilesStr); } catch (e) { /* ignore */ }
      }

      // Also query backend for all valid profiles in database to merge
      try {
        const res = await fetch(`${API_BASE}/session/profiles/all`);
        if (res.ok) {
          const data = await res.json();
          const backendProfiles: any[] = data.profiles || [];
          
          backendProfiles.forEach(bp => {
            const index = savedProfiles.findIndex(p => p.id === bp.session_id);
            if (index >= 0) {
              savedProfiles[index] = {
                ...savedProfiles[index],
                name: bp.name || savedProfiles[index].name,
                relation: bp.relation || savedProfiles[index].relation || 'Self',
                dob: bp.dob,
                birth_time: bp.birth_time,
                birth_place: bp.birth_place,
                gender: bp.gender,
                language: bp.language || 'English',
              };
            } else {
              savedProfiles.push({
                id: bp.session_id,
                name: bp.name || 'User',
                relation: bp.relation || (bp.name === 'Rishika' ? 'Self' : 'Other'),
                dob: bp.dob,
                birth_time: bp.birth_time,
                birth_place: bp.birth_place,
                gender: bp.gender,
                language: bp.language || 'English',
                isPrimary: bp.name === 'Rishika' || bp.relation === 'Self',
              });
            }
          });
        }
      } catch (err) {
        console.error('Failed to sync backend profiles:', err);
      }

      // Deduplicate by name and dob so legacy test sessions don't clutter the dropdown
      const uniqueMap = new Map<string, Profile>();
      savedProfiles.forEach(p => {
        const key = `${p.name?.toLowerCase().trim()}_${p.dob}`;
        if (!uniqueMap.has(key) || p.id === 'session_0m4d80l5hrf9') {
          uniqueMap.set(key, p);
        }
      });
      savedProfiles = Array.from(uniqueMap.values());

      // Ensure at least one profile is marked isPrimary
      if (savedProfiles.length > 0) {
        const hasPrimary = savedProfiles.some(p => p.isPrimary);
        if (!hasPrimary) {
          const rishika = savedProfiles.find(p => p.id === 'session_0m4d80l5hrf9' || p.name?.toLowerCase() === 'rishika');
          if (rishika) {
            savedProfiles.forEach(p => p.isPrimary = (p.id === rishika.id));
          } else {
            savedProfiles[0].isPrimary = true;
          }
        }
      }

      let activeSid = localStorage.getItem('call-astro_session_id');
      if (!activeSid || (savedProfiles.length > 0 && !savedProfiles.some(p => p.id === activeSid))) {
        const primary = savedProfiles.find(p => p.isPrimary) || savedProfiles[0];
        activeSid = primary ? primary.id : 'session_' + Math.random().toString(36).substring(2, 15);
        localStorage.setItem('call-astro_session_id', activeSid);
      }

      localStorage.setItem('call-astro_profiles', JSON.stringify(savedProfiles));
      setProfiles(savedProfiles);
      setSessionId(activeSid);
    };

    initApp();
  }, []);

  // 2. Fetch session data & Kundli chart whenever active sessionId changes
  useEffect(() => {
    if (!sessionId) return;

    const fetchSessionData = async () => {
      try {
        setCheckingProfile(true);
        const profileRes = await fetch(`${API_BASE}/session/${sessionId}`);
        if (profileRes.ok) {
          const profile = await profileRes.json();
          setName(profile.name);
          setRelation(profile.relation || 'Self');
          setDob(profile.dob);
          setBirthTime(profile.birth_time);
          setBirthPlace(profile.birth_place);
          setLanguage(profile.language || 'English');

          const hasDetails = Boolean(profile.dob && profile.birth_time && profile.birth_place);
          setOnboarded(hasDetails);

          // Update profiles list in memory & localStorage
          if (hasDetails) {
            setProfiles((prev: Profile[]) => {
              const index = prev.findIndex(p => p.id === sessionId);
              let updated: Profile[];
              if (index >= 0) {
                updated = prev.map(p => p.id === sessionId ? {
                  ...p,
                  name: profile.name || p.name,
                  relation: profile.relation || p.relation || 'Self',
                  dob: profile.dob,
                  birth_time: profile.birth_time,
                  birth_place: profile.birth_place,
                  language: profile.language || 'English',
                } : p);
              } else {
                const newP: Profile = {
                  id: sessionId,
                  name: profile.name || 'My Profile',
                  relation: profile.relation || 'Self',
                  dob: profile.dob,
                  birth_time: profile.birth_time,
                  birth_place: profile.birth_place,
                  language: profile.language || 'English',
                  isPrimary: prev.length === 0,
                };
                updated = [...prev, newP];
              }
              localStorage.setItem('call-astro_profiles', JSON.stringify(updated));
              return updated;
            });
          }
        }

        const historyRes = await fetch(`${API_BASE}/chat/history/${sessionId}`);
        if (historyRes.ok) {
          const history = await historyRes.json();
          setMessages(history.messages || []);
        }

        // Fetch Kundli chart for this profile
        const chartRes = await fetch(`${API_BASE}/session/${sessionId}/kundli-chart`);
        if (chartRes.ok) {
          const chartData = await chartRes.json();
          if (chartData.available) {
            setKundliPlanets(chartData.planets);
            setAscendantSign(chartData.ascendant_sign);
          } else {
            setKundliPlanets(null);
            setAscendantSign(null);
          }
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
          } else if (data.status === 'failed') {
            setChartStatus('failed');
            setChartError(data.error || 'Chart calculation failed. Please retry.');
            return;
          }
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

  // Extra safety net: after chat activity, make one more attempt to pick
  // up the chart in case the status-based poll missed the transition.
  useEffect(() => {
    if (!sessionId || chartStatus === 'ready') return;
    if (messages.length === 0) return;
    fetchChartData(sessionId).then((ready: boolean) => {
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

  // Switch to another profile
  const handleSelectProfile = (id: string) => {
    if (id === sessionId) return;
    const target = profiles.find(p => p.id === id);
    if (target) {
      setName(target.name);
      setRelation(target.relation || 'Self');
      setDob(target.dob || null);
      setBirthTime(target.birth_time || null);
      setBirthPlace(target.birth_place || null);
      setLanguage(target.language || 'English');
      setOnboarded(Boolean(target.dob && target.birth_time && target.birth_place));
    }
    stopChartPolling();
    setSessionId(id);
    localStorage.setItem('call-astro_session_id', id);
    setMessages([]);
    setKundliPlanets(null);
    setAscendantSign(null);
    setChartStatus('idle');
    setChartError(null);
    setSuggestions([]);
    setError(null);
    setTraceRefreshKey(prev => prev + 1);
  };

  // Add new profile
  const handleProfileAdded = (newProfile: Profile) => {
    setProfiles(prev => {
      const updated = [...prev, newProfile];
      localStorage.setItem('call-astro_profiles', JSON.stringify(updated));
      return updated;
    });
    setName(newProfile.name);
    setRelation(newProfile.relation);
    setDob(newProfile.dob || null);
    setBirthTime(newProfile.birth_time || null);
    setBirthPlace(newProfile.birth_place || null);
    setLanguage(newProfile.language || 'English');
    setOnboarded(true);
    setSessionId(newProfile.id);
    localStorage.setItem('call-astro_session_id', newProfile.id);
    setMessages([]);
    setKundliPlanets(null);
    setAscendantSign(null);
    setChartStatus('idle');
    setChartError(null);
    setSuggestions([]);
    setTraceRefreshKey(prev => prev + 1);
    setView('dashboard');
  };

  // Delete profile
  const handleDeleteProfile = async (id: string) => {
    try {
      await fetch(`${API_BASE}/session/${id}`, { method: 'DELETE' });
    } catch (e) {
      console.error('Failed to delete backend session:', e);
    }

    const updated = profiles.filter(p => p.id !== id);
    setProfiles(updated);
    localStorage.setItem('call-astro_profiles', JSON.stringify(updated));

    if (id === sessionId) {
      const nextProfile = updated.find(p => p.isPrimary) || updated[0];
      if (nextProfile) {
        handleSelectProfile(nextProfile.id);
      } else {
        const newSid = 'session_' + Math.random().toString(36).substring(2, 15);
        localStorage.setItem('call-astro_session_id', newSid);
        setSessionId(newSid);
        setOnboarded(false);
      }
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
        setRelation('Self');
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
    setRelation('Self');
    setOnboarded(true);
    setView('dashboard');

    const updatedProfile: Profile = {
      id: sessionId,
      name: profile.name,
      relation: 'Self',
      dob: profile.dob,
      birth_time: profile.birth_time,
      birth_place: profile.birth_place,
      language: profile.language,
      isPrimary: profiles.length === 0 || !profiles.some(p => p.isPrimary),
    };

    setProfiles(prev => {
      const index = prev.findIndex(p => p.id === sessionId);
      let updated: Profile[];
      if (index >= 0) {
        updated = prev.map(p => p.id === sessionId ? { ...p, ...updatedProfile } : p);
      } else {
        updated = [...prev, updatedProfile];
      }
      localStorage.setItem('call-astro_profiles', JSON.stringify(updated));
      return updated;
    });

    if (sessionId) {
      triggerKundliFetch(sessionId);
      pollChartStatus(sessionId);
    }
  };

  if (checkingProfile && !name && profiles.length === 0) {
    return <div className="flex h-screen items-center justify-center text-slate-400 font-medium">Loading astrological charts...</div>;
  }

  if (!onboarded) {
    return <OnboardingForm sessionId={sessionId} onComplete={handleOnboardingComplete} />;
  }

  const exportChat = () => {
    if (messages.length === 0) return;
    const textData = messages.map(msg => {
      const role = msg.role === 'user' ? (name || 'You') : 'Astrologer';
      return `[${msg.timestamp || new Date().toISOString()}] ${role}:\n${msg.content}\n`;
    }).join('\n');
    const blob = new Blob([textData], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Call-Astro_${name || 'Chat'}_Export.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const clearChat = async () => {
    if (!confirm(`Are you sure you want to clear chat history for ${name || 'this profile'}?`)) return;
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

  // ---------------- CALENDAR VIEW ----------------
  if (view === 'calendar') {
    return <AstrologyCalendar sessionId={sessionId} language={language} onBack={() => setView('dashboard')} />;
  }

  const activeProfile = profiles.find(p => p.id === sessionId);

  return (
    <div className="flex flex-col h-full bg-slate-50">
      {view === 'dashboard' ? (
        <div className="flex flex-col h-full bg-slate-50">
          <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-amber-500 text-white rounded-xl shadow-sm"><Sparkles size={20} /></div>
              <div>
                <h1 className="text-lg font-bold text-slate-800 leading-none">Call-Astro</h1>
                <p className="text-[10px] text-slate-400 font-medium mt-0.5">
                  {name ? (GREETINGS[language] || GREETINGS.English)(name) : 'Your Dashboard'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={() => setShowTransitModal(true)}
                className="flex items-center gap-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200/80 px-3 py-1.5 rounded-full text-xs font-semibold transition shadow-2xs active:scale-95"
                title="View Real-Time Planetary Transits (Gochar)"
              >
                <Globe2 size={13} className="text-indigo-600" />
                <span>Live Transits (Gochar)</span>
              </button>

              <button
                onClick={() => setView('couple')}
                className="flex items-center gap-1.5 text-xs font-semibold text-white bg-rose-500 hover:bg-rose-600 px-3 py-2 rounded-lg shadow-sm transition"
              >
                <Heart size={14} /> Couple Test
              </button>
              {kundliPlanets && ascendantSign && (
                <KundliReportButton sessionId={sessionId} language={language} name={name} />
              )}
              {profiles.length > 0 && (
                <ProfileSwitcher
                  profiles={profiles}
                  activeProfileId={sessionId}
                  onSelectProfile={handleSelectProfile}
                  onAddProfileClick={() => setShowAddProfileModal(true)}
                  onEditProfile={(p) => setProfileToEdit(p)}
                  onDeleteProfile={handleDeleteProfile}
                />
              )}
            </div>
          </header>

          <div className="flex-1 overflow-y-auto p-6">
            <div className="max-w-6xl mx-auto space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch">
                <ProfileCard
                  name={name}
                  relation={relation}
                  dob={dob}
                  birthTime={birthTime}
                  birthPlace={birthPlace}
                  language={language}
                  onReset={handleResetSession}
                  onEdit={() => setProfileToEdit(activeProfile || {
                    id: sessionId,
                    name: name || 'User',
                    relation: relation || 'Self',
                    dob,
                    birth_time: birthTime,
                    birth_place: birthPlace,
                    language,
                    isPrimary: true,
                  })}
                  isResetting={isResetting}
                />
                {renderChartPanel()}
                <LifeDashboard sessionId={sessionId} language={language} />
              </div>

              {/* Live Transits Quick Action Banner */}
              <div
                onClick={() => setShowTransitModal(true)}
                className="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 rounded-2xl p-4 sm:p-5 text-white shadow-sm border border-slate-800 flex items-center justify-between cursor-pointer hover:border-amber-400/50 transition-all group"
              >
                <div className="flex items-center gap-3.5">
                  <div className="w-10 h-10 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform">
                    <Compass size={22} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-bold text-white">Live Planetary Transits (Gochar Overlay)</h3>
                      <span className="text-[10px] bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded-full font-medium border border-amber-400/30">
                        Real-Time
                      </span>
                    </div>
                    <p className="text-xs text-slate-300 mt-0.5">
                      Check how current movements of Saturn, Jupiter & Rahu affect {name || 'you'} and all saved family charts.
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  className="hidden sm:flex items-center gap-1.5 text-xs font-semibold bg-white/10 hover:bg-white/20 text-white px-3.5 py-2 rounded-xl transition border border-white/10 shrink-0"
                >
                  <span>Open Overlay</span>
                  <Globe2 size={13} className="text-amber-400" />
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <GoToChatCard language={language} onGoToChat={() => setView('chat')} />
                <button
                  onClick={() => setView('calendar')}
                  className="w-full bg-violet-600 hover:bg-violet-700 rounded-2xl px-8 py-6 shadow-sm transition flex items-center justify-between text-left"
                >
                  <div>
                    <h3 className="text-white font-semibold text-base flex items-center gap-2">
                      <CalendarDays size={18} /> Astrology Calendar
                    </h3>
                    <p className="text-violet-100 text-sm mt-0.5">See planetary movements, Dashas & auspicious periods</p>
                  </div>
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : (
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

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <div className="p-1.5 bg-amber-500 text-white rounded-xl shadow-sm"><Sparkles size={16} /></div>
                <h1 className="text-base font-bold text-slate-800 leading-none hidden sm:block">Call-Astro</h1>
              </div>

              <button
                type="button"
                onClick={() => setShowTransitModal(true)}
                className="hidden sm:flex items-center gap-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200/80 px-2.5 py-1 rounded-full text-xs font-semibold transition"
                title="View Real-Time Planetary Transits"
              >
                <Globe2 size={12} className="text-indigo-600" />
                <span>Gochar</span>
              </button>

              {/* Relation context badge — shown when viewing a non-self profile */}
              {relation && relation !== 'Self' && (
                <span className="hidden sm:inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold border bg-rose-50 text-rose-700 border-rose-200">
                  {{Child:'👶',Partner:'❤️',Mother:'🌸',Father:'🌟',Friend:'🤝',Other:'👤'}[relation] || '👤'}
                  {' '}{relation} Profile
                </span>
              )}

              {profiles.length > 0 && (
                <ProfileSwitcher
                  profiles={profiles}
                  activeProfileId={sessionId}
                  onSelectProfile={handleSelectProfile}
                  onAddProfileClick={() => setShowAddProfileModal(true)}
                  onEditProfile={(p) => setProfileToEdit(p)}
                  onDeleteProfile={handleDeleteProfile}
                />
              )}
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
              <FaqStarter onSelect={handleSendMessage} disabled={isTyping} language={language} relation={relation} profileName={name || undefined} />
              <ChatInput onSendMessage={handleSendMessage} disabled={isTyping} language={language} />
            </main>
            <aside className="hidden lg:block w-72 border-l border-slate-200 bg-slate-50 p-4 overflow-y-auto shrink-0">
              <WeeklyGuidance sessionId={sessionId} language={language} />
              <ReasoningTrace sessionId={sessionId} refreshKey={traceRefreshKey} language={language} />
            </aside>
          </div>
        </div>
      )}

      {profileToEdit && (
        <EditDetailsModal
          sessionId={profileToEdit.id}
          currentName={profileToEdit.name}
          currentRelation={profileToEdit.relation}
          currentDob={profileToEdit.dob || null}
          currentBirthTime={profileToEdit.birth_time || null}
          currentBirthPlace={profileToEdit.birth_place || null}
          currentLanguage={profileToEdit.language || 'English'}
          currentIsPrimary={profileToEdit.isPrimary}
          onClose={() => setProfileToEdit(null)}
          onSaved={async (edited) => {
            // Update profiles list
            setProfiles(prev => {
              const updated = prev.map(p => {
                if (p.id === edited.id) {
                  return {
                    ...p,
                    name: edited.name,
                    relation: edited.relation,
                    dob: edited.dob,
                    birth_time: edited.birth_time,
                    birth_place: edited.birth_place,
                    language: edited.language,
                    isPrimary: edited.isPrimary ?? p.isPrimary,
                  };
                }
                // If this edited profile became primary, un-primary others
                if (edited.isPrimary) {
                  return { ...p, isPrimary: false };
                }
                return p;
              });
              localStorage.setItem('call-astro_profiles', JSON.stringify(updated));
              return updated;
            });

            // If active profile was updated, refresh live state
            if (edited.id === sessionId) {
              setName(edited.name);
              setRelation(edited.relation);
              setDob(edited.dob);
              setBirthTime(edited.birth_time);
              setBirthPlace(edited.birth_place);
              setLanguage(edited.language);
              setKundliPlanets(null);
              setAscendantSign(null);
              setChartStatus('idle');
              setChartError(null);

              const historyRes = await fetch(`${API_BASE}/chat/history/${sessionId}`);
              if (historyRes.ok) {
                const history = await historyRes.json();
                setMessages(history.messages || []);
              }
              pollChartStatus(sessionId);
              setTraceRefreshKey((prev: number) => prev + 1);
            }

            setProfileToEdit(null);
          }}
        />
      )}

      {showAddProfileModal && (
        <AddProfileModal
          onClose={() => setShowAddProfileModal(false)}
          onProfileAdded={handleProfileAdded}
        />
      )}

      {showTransitModal && (
        <TransitOverlayModal
          profiles={profiles}
          activeProfileId={sessionId}
          onClose={() => setShowTransitModal(false)}
          onAskAboutTransit={(question) => {
            setView('chat');
            handleSendMessage(question);
          }}
        />
      )}
    </div>
  );
}

export default App;
