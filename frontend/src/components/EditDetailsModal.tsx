import { useState } from 'react';
import { X, Star } from 'lucide-react';
import { API_BASE } from '../api';

interface EditDetailsModalProps {
  sessionId: string;
  currentName: string | null;
  currentRelation?: string | null;
  currentDob: string | null;
  currentBirthTime: string | null;
  currentBirthPlace: string | null;
  currentLanguage: string | null;
  currentIsPrimary?: boolean;
  onClose: () => void;
  onSaved: (profile: {
    id: string;
    dob: string;
    birth_time: string;
    birth_place: string;
    name: string;
    relation: string;
    language: string;
    isPrimary?: boolean;
  }) => void;
}

const RELATION_OPTIONS = [
  { value: 'Self', label: '✨ Self' },
  { value: 'Partner', label: '❤️ Partner / Spouse' },
  { value: 'Mother', label: '🌸 Mother' },
  { value: 'Father', label: '🌟 Father' },
  { value: 'Child', label: '👶 Child' },
  { value: 'Friend', label: '🤝 Friend' },
  { value: 'Other', label: '👤 Other' },
];

export default function EditDetailsModal({
  sessionId,
  currentName,
  currentRelation,
  currentDob,
  currentBirthTime,
  currentBirthPlace,
  currentLanguage,
  currentIsPrimary,
  onClose,
  onSaved,
}: EditDetailsModalProps) {
  const [name, setName] = useState(currentName || '');
  const [relation, setRelation] = useState(currentRelation || 'Self');
  const [isPrimary, setIsPrimary] = useState(Boolean(currentIsPrimary));

  const toInputDate = (d: string | null) => {
    if (!d) return '';
    const [day, month, year] = d.split('-');
    return `${year}-${month}-${day}`;
  };

  const [dob, setDob] = useState(toInputDate(currentDob));
  const [birthTime, setBirthTime] = useState(currentBirthTime || '');
  const [birthPlace, setBirthPlace] = useState(currentBirthPlace || '');
  const [language, setLanguage] = useState(currentLanguage || 'Hinglish');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSave = async () => {
    setError('');
    if (!name.trim() || !dob || !birthTime || !birthPlace.trim() || !language.trim()) {
      setError('Please fill in all fields.');
      return;
    }
    setSaving(true);
    try {
      const [year, month, day] = dob.split('-');
      const formattedDob = `${day}-${month}-${year}`;

      const response = await fetch(`${API_BASE}/session/${sessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          relation,
          dob: formattedDob,
          birth_time: birthTime,
          birth_place: birthPlace.trim(),
          language: language.trim(),
        }),
      });
      if (!response.ok) throw new Error('Failed to update details.');
      const saved = await response.json();

      // Trigger fresh chart calculation right away
      await fetch(`${API_BASE}/session/${sessionId}/recalculate-kundli`, { method: 'POST' });

      onSaved({
        id: sessionId,
        dob: saved.dob,
        birth_time: saved.birth_time,
        birth_place: saved.birth_place,
        name: saved.name,
        relation: saved.relation || relation,
        language: saved.language,
        isPrimary,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center z-50 px-4">
      <div className="bg-white rounded-3xl p-6 sm:p-7 w-full max-w-sm shadow-2xl border border-slate-100 animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-4">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-slate-800">Edit Profile & Chart</h2>
            {isPrimary && (
              <span className="text-[10px] bg-amber-100 text-amber-700 font-bold px-1.5 py-0.5 rounded">
                Primary
              </span>
            )}
          </div>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600 rounded-lg">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2.5">
            <div>
              <label className="block text-xs font-semibold text-slate-500 mb-1">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs focus:outline-hidden focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 mb-1">Relation</label>
              <select
                value={relation}
                onChange={(e) => setRelation(e.target.value)}
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs bg-white focus:outline-hidden focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500"
              >
                {RELATION_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">Date of Birth</label>
            <input
              type="date"
              value={dob}
              onChange={(e) => setDob(e.target.value)}
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs focus:outline-hidden focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">Birth Time</label>
            <input
              type="time"
              value={birthTime}
              onChange={(e) => setBirthTime(e.target.value)}
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs focus:outline-hidden focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">Birth Place</label>
            <input
              value={birthPlace}
              onChange={(e) => setBirthPlace(e.target.value)}
              placeholder="City, Country"
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs focus:outline-hidden focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">Language</label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs bg-white focus:outline-hidden focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500"
            >
              <option value="English">English</option>
              <option value="Hindi">हिंदी (Hindi)</option>
              <option value="Hinglish">Hinglish</option>
            </select>
          </div>

          <div className="pt-1">
            <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-600">
              <input
                type="checkbox"
                checked={isPrimary}
                onChange={(e) => setIsPrimary(e.target.checked)}
                className="w-3.5 h-3.5 rounded text-amber-500 focus:ring-amber-400"
              />
              <span className="flex items-center gap-1 font-medium">
                <Star size={12} className={isPrimary ? 'fill-amber-400 text-amber-500' : 'text-slate-400'} />
                Set as Default / Primary Profile
              </span>
            </label>
          </div>
        </div>

        {error && <p className="text-xs text-rose-500 mt-3 bg-rose-50 p-2 rounded-xl">{error}</p>}

        <div className="flex gap-2.5 mt-5">
          <button
            onClick={onClose}
            className="flex-1 rounded-xl border border-slate-200 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex-1 rounded-xl bg-slate-900 hover:bg-slate-800 py-2 text-xs font-semibold text-white disabled:opacity-50 transition"
          >
            {saving ? 'Recalculating...' : 'Save Changes'}
          </button>
        </div>
        <p className="text-[10px] text-slate-400 text-center mt-2.5">
          Recalculates Vedic chart & Dasha for this profile.
        </p>
      </div>
    </div>
  );
}
