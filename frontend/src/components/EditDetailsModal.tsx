import { useState } from 'react';

interface EditDetailsModalProps {
  sessionId: string;
  currentName: string | null;
  currentDob: string | null;
  currentBirthTime: string | null;
  currentBirthPlace: string | null;
  currentLanguage: string | null;
  onClose: () => void;
  onSaved: (profile: { dob: string; birth_time: string; birth_place: string; name: string; language: string }) => void;
}

export default function EditDetailsModal({
  sessionId, currentName, currentDob, currentBirthTime, currentBirthPlace, currentLanguage, onClose, onSaved
}: EditDetailsModalProps) {
  const [name, setName] = useState(currentName || '');
  const toInputDate = (d: string | null) => {
    if (!d) return '';
    const [day, month, year] = d.split('-');
    return `${year}-${month}-${day}`;
  };
  const [dob, setDob] = useState(toInputDate(currentDob));
  const [birthTime, setBirthTime] = useState(currentBirthTime || '');
  const [birthPlace, setBirthPlace] = useState(currentBirthPlace || '');
  const [language, setLanguage] = useState(currentLanguage || '');
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

      const response = await fetch(`/api/session/${sessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), dob: formattedDob, birth_time: birthTime, birth_place: birthPlace.trim(), language: language.trim() }),
      });
      if (!response.ok) throw new Error('Failed to update details.');
      const saved = await response.json();

      // Trigger fresh chart calculation right away
      await fetch(`/api/session/${sessionId}/recalculate-kundli`, { method: 'POST' });

      onSaved({ dob: saved.dob, birth_time: saved.birth_time, birth_place: saved.birth_place, name: saved.name, language: saved.language });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 px-4">
      <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-lg">
        <h2 className="text-lg font-bold text-slate-800 mb-4">Edit Your Details</h2>
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Date of Birth</label>
            <input type="date" value={dob} onChange={(e) => setDob(e.target.value)} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Birth Time</label>
            <input type="time" value={birthTime} onChange={(e) => setBirthTime(e.target.value)} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Birth Place</label>
            <input value={birthPlace} onChange={(e) => setBirthPlace(e.target.value)} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Language</label>
            <input value={language} onChange={(e) => setLanguage(e.target.value)} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
          </div>
        </div>

        {error && <p className="text-sm text-rose-500 mt-3">{error}</p>}

        <div className="flex gap-2 mt-5">
          <button onClick={onClose} className="flex-1 rounded-xl border border-slate-200 py-2.5 text-sm font-medium text-slate-600">Cancel</button>
          <button onClick={handleSave} disabled={saving} className="flex-1 rounded-xl bg-slate-900 py-2.5 text-sm font-medium text-white disabled:opacity-50">
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
        <p className="text-[10px] text-slate-400 text-center mt-3">Changing your birth details will recalculate your chart.</p>
      </div>
    </div>
  );
}