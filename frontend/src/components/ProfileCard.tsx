import React from 'react';
import { Calendar, Clock, MapPin, Globe, RotateCcw, Pencil } from 'lucide-react';

interface ProfileCardProps {
  dob: string | null;
  birthTime: string | null;
  birthPlace: string | null;
  language: string;
  onReset: () => void;
  onEdit: () => void;
  isResetting: boolean;
}

const STRINGS: Record<string, {
  title: string;
  editButton: string;
  resetButton: string;
  dobLabel: string;
  timeLabel: string;
  placeLabel: string;
  languageLabel: string;
  pending: string;
}> = {
  English: {
    title: 'Profile',
    editButton: 'Update',
    resetButton: 'Reset',
    dobLabel: 'Date of Birth',
    timeLabel: 'Time of Birth',
    placeLabel: 'Place of Birth',
    languageLabel: 'Language',
    pending: 'Pending...',
  },
  Hindi: {
    title: 'प्रोफ़ाइल',
    editButton: 'अपडेट करें',
    resetButton: 'रीसेट',
    dobLabel: 'जन्म तिथि',
    timeLabel: 'जन्म समय',
    placeLabel: 'जन्म स्थान',
    languageLabel: 'भाषा',
    pending: 'लंबित...',
  },
  Hinglish: {
    title: 'Profile',
    editButton: 'Update Karein',
    resetButton: 'Reset',
    dobLabel: 'Janm Tithi',
    timeLabel: 'Janm Samay',
    placeLabel: 'Janm Sthaan',
    languageLabel: 'Language',
    pending: 'Pending...',
  },
};

export const ProfileCard: React.FC<ProfileCardProps> = ({
  dob, birthTime, birthPlace, language, onReset, onEdit, isResetting
}) => {
  const t = STRINGS[language] || STRINGS.Hinglish;

  return (
    <div className="w-full bg-white border border-slate-200 rounded-2xl p-6 shadow-sm h-full">
      <div className="flex justify-between items-center mb-6">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">{t.title}</h3>
        <div className="flex gap-2">
          <button onClick={onEdit} className="text-xs flex items-center gap-1.5 text-slate-600 hover:text-slate-800 bg-slate-50 hover:bg-slate-100 px-2.5 py-1.5 rounded-lg font-medium transition">
            <Pencil size={12} /> {t.editButton}
          </button>
          <button onClick={onReset} disabled={isResetting}
            className="text-xs flex items-center gap-1.5 text-rose-600 hover:text-rose-700 bg-rose-50 hover:bg-rose-100 disabled:opacity-50 px-2.5 py-1.5 rounded-lg font-medium transition">
            <RotateCcw size={12} className={isResetting ? 'animate-spin' : ''} /> {t.resetButton}
          </button>
        </div>
      </div>

      <div className="space-y-4">
        <div className="flex items-start gap-3">
          <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg mt-0.5"><Calendar size={16} /></div>
          <div>
            <div className="text-xs text-slate-400 font-medium">{t.dobLabel}</div>
            <div className={`text-sm font-medium mt-0.5 ${dob ? 'text-slate-800' : 'text-slate-400 italic'}`}>{dob || t.pending}</div>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="p-2 bg-amber-50 text-amber-600 rounded-lg mt-0.5"><Clock size={16} /></div>
          <div>
            <div className="text-xs text-slate-400 font-medium">{t.timeLabel}</div>
            <div className={`text-sm font-medium mt-0.5 ${birthTime ? 'text-slate-800' : 'text-slate-400 italic'}`}>{birthTime || t.pending}</div>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="p-2 bg-emerald-50 text-emerald-600 rounded-lg mt-0.5"><MapPin size={16} /></div>
          <div>
            <div className="text-xs text-slate-400 font-medium">{t.placeLabel}</div>
            <div className={`text-sm font-medium mt-0.5 ${birthPlace ? 'text-slate-800' : 'text-slate-400 italic'}`}>{birthPlace || t.pending}</div>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="p-2 bg-sky-50 text-sky-600 rounded-lg mt-0.5"><Globe size={16} /></div>
          <div>
            <div className="text-xs text-slate-400 font-medium">{t.languageLabel}</div>
            <div className="text-sm font-medium mt-0.5 text-slate-800 capitalize">{language}</div>
          </div>
        </div>
      </div>
    </div>
  );
};