import { useState } from 'react';
import { UserPlus, Sparkles, X } from 'lucide-react';
import { Profile } from './ProfileSwitcher';
import { API_BASE } from '../api';

interface AddProfileModalProps {
  onClose: () => void;
  onProfileAdded: (newProfile: Profile) => void;
}

const RELATION_OPTIONS = [
  { value: 'Partner', label: '❤️ Partner / Spouse' },
  { value: 'Mother', label: '🌸 Mother' },
  { value: 'Father', label: '🌟 Father' },
  { value: 'Child', label: '👶 Child' },
  { value: 'Friend', label: '🤝 Friend' },
  { value: 'Other', label: '👤 Other' },
];

export default function AddProfileModal({ onClose, onProfileAdded }: AddProfileModalProps) {
  const [name, setName] = useState('');
  const [relation, setRelation] = useState('Partner');
  const [dob, setDob] = useState('');
  const [birthTime, setBirthTime] = useState('');
  const [birthPlace, setBirthPlace] = useState('');
  const [gender, setGender] = useState('Female');
  const [language, setLanguage] = useState('Hinglish');

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!name.trim()) {
      setError('Please enter a name.');
      return;
    }
    if (!dob || !birthTime || !birthPlace.trim()) {
      setError('Please fill in Date, Time, and Place of birth for accurate Kundli calculations.');
      return;
    }

    setSaving(true);
    try {
      // Generate a new isolated session_id for this person
      const newSessionId = 'session_' + Math.random().toString(36).substring(2, 15);

      // Convert YYYY-MM-DD to DD-MM-YYYY
      const [year, month, day] = dob.split('-');
      const formattedDob = `${day}-${month}-${year}`;

      const payload = {
        name: name.trim(),
        relation,
        dob: formattedDob,
        birth_time: birthTime,
        birth_place: birthPlace.trim(),
        gender,
        language,
      };

      // 1. Initialize session and save profile in backend database
      const res = await fetch(`${API_BASE}/session/${newSessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error('Failed to save profile on backend.');
      }

      // 2. Trigger Kundli and Dasha calculations for this new chart
      await fetch(`${API_BASE}/session/${newSessionId}/recalculate-kundli`, {
        method: 'POST',
      });

      const newProfile: Profile = {
        id: newSessionId,
        name: name.trim(),
        relation,
        dob: formattedDob,
        birth_time: birthTime,
        birth_place: birthPlace.trim(),
        gender,
        language,
        isPrimary: false,
      };

      onProfileAdded(newProfile);
      onClose();
    } catch (err: any) {
      console.error('Error adding profile:', err);
      setError(err.message || 'Something went wrong saving the profile.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-xs flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-3xl p-6 sm:p-7 w-full max-w-md shadow-2xl border border-slate-100 animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between pb-4 border-b border-slate-100 mb-5">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-2xl bg-amber-500 text-white flex items-center justify-center shadow-sm shadow-amber-200">
              <UserPlus size={18} />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-800">Add New Chart Profile</h2>
              <p className="text-xs text-slate-400">Save birth details for family or partner</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-xl transition"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSave} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Full Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Aman"
                className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm focus:outline-hidden focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 transition"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Relation</label>
              <select
                value={relation}
                onChange={(e) => setRelation(e.target.value)}
                className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm bg-white focus:outline-hidden focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 transition"
              >
                {RELATION_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Date of Birth</label>
              <input
                type="date"
                value={dob}
                onChange={(e) => setDob(e.target.value)}
                className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm focus:outline-hidden focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 transition"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Time of Birth</label>
              <input
                type="time"
                value={birthTime}
                onChange={(e) => setBirthTime(e.target.value)}
                className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm focus:outline-hidden focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 transition"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Place of Birth (City, State/Country)</label>
            <input
              type="text"
              value={birthPlace}
              onChange={(e) => setBirthPlace(e.target.value)}
              placeholder="e.g. New Delhi, India"
              className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm focus:outline-hidden focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 transition"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Gender</label>
              <select
                value={gender}
                onChange={(e) => setGender(e.target.value)}
                className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm bg-white focus:outline-hidden focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 transition"
              >
                <option value="Female">Female</option>
                <option value="Male">Male</option>
                <option value="Other">Other</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Language</label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm bg-white focus:outline-hidden focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 transition"
              >
                <option value="Hinglish">Hinglish</option>
                <option value="English">English</option>
                <option value="Hindi">हिंदी (Hindi)</option>
              </select>
            </div>
          </div>

          {error && <p className="text-xs text-rose-500 bg-rose-50 p-2.5 rounded-xl border border-rose-100">{error}</p>}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-xl border border-slate-200 py-2.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex-1 rounded-xl bg-slate-900 hover:bg-slate-800 py-2.5 text-xs font-semibold text-white disabled:opacity-50 flex items-center justify-center gap-1.5 shadow-sm transition active:scale-[0.98]"
            >
              {saving ? (
                <span>Calculating Chart...</span>
              ) : (
                <>
                  <Sparkles size={14} className="text-amber-400" />
                  <span>Save & Load Chart</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
