import { useState, useEffect } from 'react';
import { X, Globe2, Compass, Sparkles, MessageCircle, RefreshCw } from 'lucide-react';

import { Profile } from './ProfileSwitcher';
import { API_BASE } from '../api';

interface TransitOverlayModalProps {
  profiles: Profile[];
  activeProfileId: string;
  onClose: () => void;
  onAskAboutTransit?: (question: string) => void;
}

interface SkyPlanet {
  name: string;
  sign: string;
  degree?: number;
  nakshatra?: string;
  is_retrograde?: boolean;
}

interface TransitDetail {
  name: string;
  current_sign: string;
  degree?: number;
  nakshatra?: string;
  is_retrograde?: boolean;
  lagna_house: number;
  lagna_house_desc: string;
  moon_house: number;
  is_favorable: boolean;
}

interface TransitInsight {
  book: string;
  snippet: string;
  score: number;
}

interface ProfileOverlay {
  available: boolean;
  profile_name: string;
  relation: string;
  natal_ascendant: string;
  natal_moon_sign: string;
  transit_date: string;
  transits: TransitDetail[];
  transit_insights: TransitInsight[];
}


const PLANET_ICONS: Record<string, string> = {
  Sun: '☀️',
  Moon: '🌙',
  Mars: '🔴',
  Mercury: '🟢',
  Jupiter: '✨',
  Venus: '💖',
  Saturn: '🪐',
  Rahu: '🐉',
  Ketu: '☄️',
};

export default function TransitOverlayModal({
  profiles,
  activeProfileId,
  onClose,
  onAskAboutTransit,
}: TransitOverlayModalProps) {
  const [selectedProfileId, setSelectedProfileId] = useState<string>(activeProfileId);
  const [skyPlanets, setSkyPlanets] = useState<SkyPlanet[]>([]);
  const [overlays, setOverlays] = useState<Record<string, ProfileOverlay>>({});
  const [loading, setLoading] = useState(true);
  const [transitDate, setTransitDate] = useState<string>('');
  const [viewMode, setViewMode] = useState<'individual' | 'comparison'>('individual');

  useEffect(() => {
    const fetchTransits = async () => {
      try {
        setLoading(true);
        const res = await fetch(`${API_BASE}/session/transits/live`);
        if (res.ok) {
          const data = await res.json();
          setSkyPlanets(data.sky_planets || []);
          setTransitDate(data.date || '');

          const overlayMap: Record<string, ProfileOverlay> = {};
          (data.overlays || []).forEach((ov: ProfileOverlay) => {
            // Match with profile by name
            const prof = profiles.find((p) => p.name === ov.profile_name);
            if (prof) {
              overlayMap[prof.id] = ov;
            } else {
              overlayMap[ov.profile_name] = ov;
            }
          });
          setOverlays(overlayMap);
        }
      } catch (e) {
        console.error('Failed to load transit data:', e);
      } finally {
        setLoading(false);
      }
    };

    fetchTransits();
  }, [profiles]);

  const activeOverlay = overlays[selectedProfileId] || Object.values(overlays)[0];
  const selectedProfile = profiles.find((p) => p.id === selectedProfileId);

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-center justify-center z-50 p-3 sm:p-5">
      <div className="bg-white rounded-3xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl border border-slate-100 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between shrink-0 bg-gradient-to-r from-slate-900 to-slate-800 text-white">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center justify-center">
              <Globe2 size={22} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold">Real-Time Planetary Transits (Gochar)</h2>
                {transitDate && (
                  <span className="text-[10px] bg-amber-400/20 text-amber-300 px-2 py-0.5 rounded-full font-medium border border-amber-400/30">
                    Live: {transitDate}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-300 mt-0.5">
                Current sky movements overlaid on natal charts
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="bg-slate-800 p-0.5 rounded-xl border border-slate-700 hidden sm:flex">
              <button
                onClick={() => setViewMode('individual')}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition ${
                  viewMode === 'individual' ? 'bg-amber-500 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                Chart Overlay
              </button>
              <button
                onClick={() => setViewMode('comparison')}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition ${
                  viewMode === 'comparison' ? 'bg-amber-500 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                Family Matrix ({profiles.length})
              </button>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-xl transition"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-6">
          {/* Live Sky Planets Pill Carousel */}
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Compass size={14} className="text-amber-500" /> Current Positions in the Sky
              </h3>
              <span className="text-[11px] text-slate-400">Sidereal Lahiri Zodiac</span>
            </div>

            <div className="grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-9 gap-2">
              {skyPlanets.map((p) => (
                <div
                  key={p.name}
                  className="bg-slate-50 border border-slate-200/80 rounded-2xl p-2.5 text-center flex flex-col items-center shadow-2xs hover:border-amber-300 transition"
                >
                  <span className="text-base mb-1">{PLANET_ICONS[p.name] || '🪐'}</span>
                  <div className="text-xs font-bold text-slate-800 leading-tight flex items-center gap-1">
                    {p.name}
                    {p.is_retrograde && (
                      <span className="text-[9px] text-rose-500 font-bold" title="Retrograde">
                        (R)
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-amber-700 font-semibold mt-0.5">{p.sign}</div>
                  {p.nakshatra && (
                    <div className="text-[9px] text-slate-400 truncate max-w-[75px] mt-0.5">
                      {p.nakshatra}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {viewMode === 'individual' ? (
            <>
              {/* Profile Selector Tabs */}
              <div className="flex items-center gap-2 border-b border-slate-100 pb-3 overflow-x-auto">
                {profiles.map((p) => {
                  const isSelected = p.id === selectedProfileId;

                  return (
                    <button
                      key={p.id}
                      onClick={() => setSelectedProfileId(p.id)}
                      className={`flex items-center gap-2 px-3.5 py-2 rounded-2xl text-xs font-semibold whitespace-nowrap transition border ${
                        isSelected
                          ? 'bg-amber-50 border-amber-300 text-amber-900 shadow-xs'
                          : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      <span>{p.name}</span>
                      <span className="text-[10px] text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded-md">
                        {p.relation}
                      </span>
                    </button>
                  );
                })}
              </div>

              {loading ? (
                <div className="py-12 flex flex-col items-center justify-center text-slate-400 text-sm gap-2">
                  <RefreshCw size={20} className="animate-spin text-amber-500" />
                  <span>Calculating real-time Gochar house placements...</span>
                </div>
              ) : activeOverlay ? (
                <div className="space-y-5">
                  {/* Chart Meta — Lagna + Moon */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold text-sm">
                        Lagna
                      </div>
                      <div>
                        <div className="text-[11px] text-slate-400 font-medium">Natal Ascendant</div>
                        <div className="text-sm font-bold text-slate-800">
                          {activeOverlay.natal_ascendant} Lagna
                        </div>
                      </div>
                    </div>

                    <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center font-bold text-sm">
                        Moon
                      </div>
                      <div>
                        <div className="text-[11px] text-slate-400 font-medium">Natal Moon Sign</div>
                        <div className="text-sm font-bold text-slate-800">
                          {activeOverlay.natal_moon_sign || 'Not available'}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Transit Insights — RAG-retrieved book passages */}
                  {activeOverlay.transit_insights && activeOverlay.transit_insights.length > 0 && (
                    <div className="bg-gradient-to-br from-amber-500/10 to-orange-500/5 border border-amber-200/80 rounded-2xl p-4">
                      <div className="text-xs font-bold uppercase tracking-wider text-amber-800 flex items-center gap-1.5 mb-3">
                        <Sparkles size={14} className="text-amber-600" />
                        Key Transit Insights for {activeOverlay.profile_name}
                      </div>
                      <div className="space-y-3">
                        {activeOverlay.transit_insights.map((insight, i) => (
                          <div key={i} className="bg-white/70 rounded-xl border border-amber-100 p-3">
                            <p className="text-xs text-slate-700 leading-relaxed italic">
                              "{insight.snippet}"
                            </p>
                            <div className="flex items-center gap-1 mt-2">
                              <span className="text-[9px] font-bold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full border border-amber-200">
                                📚 {insight.book}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}


                  {/* House Transits Grid */}
                  <div>
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
                      Active House Transits from Natal Ascendant ({activeOverlay.natal_ascendant})
                    </h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                      {activeOverlay.transits.map((t) => (
                        <div
                          key={t.name}
                          className="bg-white border border-slate-200 rounded-2xl p-3.5 shadow-2xs hover:shadow-xs transition"
                        >
                          <div className="flex items-center justify-between mb-1.5">
                            <div className="flex items-center gap-2">
                              <span className="text-base">{PLANET_ICONS[t.name] || '🪐'}</span>
                              <span className="text-xs font-bold text-slate-800">
                                {t.name} {t.is_retrograde && <span className="text-rose-500 text-[10px]">(R)</span>}
                              </span>
                            </div>
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                t.is_favorable
                                  ? 'bg-emerald-100 text-emerald-700'
                                  : 'bg-slate-100 text-slate-600'
                              }`}
                            >
                              {t.is_favorable ? 'Benefic' : 'Neutral'}
                            </span>
                          </div>
                          <div className="text-xs font-semibold text-slate-700">
                            {t.lagna_house_desc}
                          </div>
                          <div className="text-[11px] text-slate-400 mt-0.5">
                            In {t.current_sign} • {t.moon_house}th from Moon
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-10 text-slate-400 text-xs">
                  Chart calculation required for transit overlay.
                </div>
              )}
            </>
          ) : (
            /* Multi-Profile Comparison Matrix */
            <div className="space-y-4">
              <div className="text-xs text-slate-500 font-medium">
                Compare today's major planetary transits across all family members and partners at a glance:
              </div>

              <div className="overflow-x-auto border border-slate-200 rounded-2xl">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase text-[10px] tracking-wider">
                    <tr>
                      <th className="px-4 py-3">Profile</th>
                      <th className="px-4 py-3">Lagna / Moon</th>
                      <th className="px-4 py-3">🪐 Saturn Transit</th>
                      <th className="px-4 py-3">✨ Jupiter Transit</th>
                      <th className="px-4 py-3">⚡ Rahu / Ketu</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {profiles.map((p) => {
                      const ov = overlays[p.id];
                      const saturn = ov?.transits?.find((t) => t.name === 'Saturn');
                      const jupiter = ov?.transits?.find((t) => t.name === 'Jupiter');
                      const rahu = ov?.transits?.find((t) => t.name === 'Rahu');

                      return (
                        <tr key={p.id} className="hover:bg-slate-50/80 transition">
                          <td className="px-4 py-3 font-bold text-slate-800">
                            <div className="flex items-center gap-1.5">
                              <span>{p.name}</span>
                              <span className="text-[9px] bg-slate-100 text-slate-500 px-1 py-0.5 rounded">
                                {p.relation}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {ov?.natal_ascendant ? `${ov.natal_ascendant} / ${ov.natal_moon_sign}` : '—'}
                          </td>
                          <td className="px-4 py-3 text-slate-700">
                            {saturn ? `${saturn.lagna_house_desc.split(' ')[0]} in ${saturn.current_sign}` : '—'}
                          </td>
                          <td className="px-4 py-3 text-slate-700">
                            {jupiter ? `${jupiter.lagna_house_desc.split(' ')[0]} in ${jupiter.current_sign}` : '—'}
                          </td>
                          <td className="px-4 py-3 text-slate-700">
                            {rahu ? `${rahu.lagna_house_desc.split(' ')[0]} in ${rahu.current_sign}` : '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>


        {/* Footer Action */}
        <div className="px-6 py-3.5 border-t border-slate-100 bg-slate-50 flex items-center justify-between shrink-0">
          <div className="text-[11px] text-slate-400">
            Real-time planetary data calculated according to Vedic Gochar principles.
          </div>

          <div className="flex gap-2">
            {onAskAboutTransit && selectedProfile && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onAskAboutTransit(
                    `How are current planetary transits and Saturn/Jupiter affecting ${selectedProfile.name} right now?`
                  );
                }}
                className="flex items-center gap-1.5 text-xs font-semibold bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 rounded-xl transition shadow-xs active:scale-95"
              >
                <MessageCircle size={14} className="text-amber-400" />
                <span>Ask Astrologer About {selectedProfile.name}'s Transits</span>
              </button>
            )}
            <button
              onClick={onClose}
              className="text-xs font-semibold text-slate-600 hover:bg-slate-200 bg-slate-100 px-4 py-2 rounded-xl transition"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
