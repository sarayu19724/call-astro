import { useState } from 'react';

interface OnboardingFormProps {
  sessionId: string;
  onComplete: (profile: { dob: string; birth_time: string; birth_place: string; language: string; name: string }) => void;
}

const LANGUAGES = [
  { value: 'English', label: 'English' },
  { value: 'Hindi', label: 'हिंदी (Hindi)' },
  { value: 'Hinglish', label: 'Hinglish' },
];

const STRINGS: Record<string, {
  title: string;
  subtitle: string;
  languageLabel: string;
  nameLabel: string;
  namePlaceholder: string;
  dobLabel: string;
  timeLabel: string;
  placeLabel: string;
  placePlaceholder: string;
  errorRequired: string;
  errorGeneric: string;
  submitIdle: string;
  submitLoading: string;
}> = {
  English: {
    title: '🙏 Namaste!',
    subtitle: 'Share your birth details so I can prepare your Kundali.',
    languageLabel: 'Preferred Language',
    nameLabel: 'Name',
    namePlaceholder: 'Your name',
    dobLabel: 'Date of Birth 📅',
    timeLabel: 'Birth Time ⏰',
    placeLabel: 'Birth Place 📍',
    placePlaceholder: 'e.g. Lucknow',
    errorRequired: 'Please fill in all fields.',
    errorGeneric: 'Something went wrong.',
    submitIdle: 'Start Chatting',
    submitLoading: 'Saving...',
  },
  Hindi: {
    title: '🙏 नमस्ते!',
    subtitle: 'अपनी कुंडली तैयार करने के लिए अपना जन्म विवरण साझा करें।',
    languageLabel: 'पसंदीदा भाषा',
    nameLabel: 'नाम',
    namePlaceholder: 'आपका नाम',
    dobLabel: 'जन्म तिथि 📅',
    timeLabel: 'जन्म समय ⏰',
    placeLabel: 'जन्म स्थान 📍',
    placePlaceholder: 'जैसे लखनऊ',
    errorRequired: 'कृपया सभी फ़ील्ड भरें।',
    errorGeneric: 'कुछ गलत हो गया।',
    submitIdle: 'बात शुरू करें',
    submitLoading: 'सेव हो रहा है...',
  },
  Hinglish: {
    title: '🙏 Namaste!',
    subtitle: 'Apni Kundali taiyaar karne ke liye janm vivaran share karein.',
    languageLabel: 'Pasandeeda Bhasha',
    nameLabel: 'Naam',
    namePlaceholder: 'Aapka naam',
    dobLabel: 'Janm Tithi 📅',
    timeLabel: 'Janm Samay ⏰',
    placeLabel: 'Janm Sthaan 📍',
    placePlaceholder: 'jaise Lucknow',
    errorRequired: 'Kripya sabhi fields bharein.',
    errorGeneric: 'Kuch galat ho gaya.',
    submitIdle: 'Chat Shuru Karein',
    submitLoading: 'Save ho raha hai...',
  },
};

export default function OnboardingForm({ sessionId, onComplete }: OnboardingFormProps) {
  const [language, setLanguage] = useState('Hinglish');
  const [name, setName] = useState('');
  const [dob, setDob] = useState('');
  const [birthTime, setBirthTime] = useState('');
  const [birthPlace, setBirthPlace] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const t = STRINGS[language] || STRINGS.Hinglish;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!name.trim() || !dob || !birthTime || !birthPlace.trim()) {
      setError(t.errorRequired);
      return;
    }

    setLoading(true);
    try {
      const [year, month, day] = dob.split('-');
      const formattedDob = `${day}-${month}-${year}`;

      const response = await fetch(`/api/session/${sessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          dob: formattedDob,
          birth_time: birthTime,
          birth_place: birthPlace.trim(),
          language,
        }),
      });

      if (!response.ok) {
        throw new Error(t.errorGeneric);
      }

      const saved = await response.json();
      onComplete({
        dob: saved.dob,
        birth_time: saved.birth_time,
        birth_place: saved.birth_place,
        language: saved.language,
        name: saved.name,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t.errorGeneric);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-sm border border-slate-200">
        <h1 className="mb-1 text-2xl font-bold text-slate-800">{t.title}</h1>
        <p className="mb-6 text-sm text-slate-400">{t.subtitle}</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">{t.languageLabel}</label>
            <div className="flex gap-2">
              {LANGUAGES.map((lang) => (
                <button
                  key={lang.value}
                  type="button"
                  onClick={() => setLanguage(lang.value)}
                  className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium transition ${
                    language === lang.value
                      ? 'border-slate-800 bg-slate-800 text-white'
                      : 'border-slate-200 text-slate-600 hover:border-slate-300'
                  }`}
                >
                  {lang.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">{t.nameLabel}</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t.namePlaceholder}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-slate-400 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">{t.dobLabel}</label>
            <input
              type="date"
              value={dob}
              onChange={(e) => setDob(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-slate-400 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">{t.timeLabel}</label>
            <input
              type="time"
              value={birthTime}
              onChange={(e) => setBirthTime(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-slate-400 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">{t.placeLabel}</label>
            <input
              type="text"
              value={birthPlace}
              onChange={(e) => setBirthPlace(e.target.value)}
              placeholder={t.placePlaceholder}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-slate-400 focus:outline-none"
            />
          </div>

          {error && <p className="text-sm text-rose-500">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-slate-900 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
          >
            {loading ? t.submitLoading : t.submitIdle}
          </button>
        </form>
      </div>
    </div>
  );
}