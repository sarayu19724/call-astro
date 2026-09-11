import React from 'react';
import { Calendar, Clock, MapPin, Globe, RotateCcw, Pencil } from 'lucide-react';

interface ProfileCardProps {
  name?: string | null;
  relation?: string | null;
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
    title: 'Profile Details',
    editButton: 'Update',
    resetButton: 'Reset',
    dobLabel: 'Date of Birth',
    timeLabel: 'Time of Birth',
    placeLabel: 'Place of Birth',
    languageLabel: 'Language',
    pending: 'Pending...',
  },
  Hindi: {
    title: 'प्रोफ़ाइल विवरण',
    editButton: 'अपडेट करें',
    resetButton: 'रीसेट',
    dobLabel: 'जन्म तिथि',
    timeLabel: 'जन्म समय',
    placeLabel: 'जन्म स्थान',
    languageLabel: 'भाषा',
    pending: 'लंबित...',
  },
  Hinglish: {
    title: 'Profile Details',
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
  name, relation, dob, birthTime, birthPlace, language, onReset, onEdit, isResetting
}) => {
  const t = STRINGS[language] || STRINGS.Hinglish;

  return (
    <div className="w-full bg-white border border-slate-200 rounded-2xl p-6 shadow-sm h-full flex flex-col justify-between">
      <div>
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">{t.title}</h3>
            {relation && (
              <span className="text-[10px] uppercase font-bold bg-amber-50 text-amber-700 border border-amber-200/60 px-2 py-0.5 rounded-full">
                {relation}
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <button onClick={onEdit} className="text-xs flex items-center gap-1 text-slate-600 hover:text-slate-800 bg-slate-50 hover:bg-slate-100 px-2 py-1 rounded-lg font-medium transition">
              <Pencil size={11} /> {t.editButton}
            </button>
            <button onClick={onReset} disabled={isResetting}
              className="text-xs flex items-center gap-1 text-rose-600 hover:text-rose-700 bg-rose-50 hover:bg-rose-100 disabled:opacity-50 px-2 py-1 rounded-lg font-medium transition"
              title="Reset profile history">
              <RotateCcw size={11} className={isResetting ? 'animate-spin' : ''} /> {t.resetButton}
            </button>
          </div>
        </div>

        {name && (
          <div className="mb-4 pb-3 border-b border-slate-100 flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center font-bold text-xs border border-slate-200">
              {name.charAt(0).toUpperCase()}
            </div>
            <div>
              <div className="text-sm font-bold text-slate-800 leading-tight">{name}</div>
              <div className="text-[11px] text-slate-400">Active Natal Chart</div>
            </div>
          </div>
        )}

        <div className="space-y-3">
          <div className="flex items-start gap-3">
            <div className="p-1.5 bg-indigo-50 text-indigo-600 rounded-lg mt-0.5"><Calendar size={14} /></div>
            <div>
              <div className="text-[11px] text-slate-400 font-medium">{t.dobLabel}</div>
              <div className={`text-xs font-semibold mt-0.5 ${dob ? 'text-slate-800' : 'text-slate-400 italic'}`}>{dob || t.pending}</div>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <div className="p-1.5 bg-amber-50 text-amber-600 rounded-lg mt-0.5"><Clock size={14} /></div>
            <div>
              <div className="text-[11px] text-slate-400 font-medium">{t.timeLabel}</div>
              <div className={`text-xs font-semibold mt-0.5 ${birthTime ? 'text-slate-800' : 'text-slate-400 italic'}`}>{birthTime || t.pending}</div>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <div className="p-1.5 bg-emerald-50 text-emerald-600 rounded-lg mt-0.5"><MapPin size={14} /></div>
            <div>
              <div className="text-[11px] text-slate-400 font-medium">{t.placeLabel}</div>
              <div className={`text-xs font-semibold mt-0.5 ${birthPlace ? 'text-slate-800' : 'text-slate-400 italic'}`}>{birthPlace || t.pending}</div>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <div className="p-1.5 bg-sky-50 text-sky-600 rounded-lg mt-0.5"><Globe size={14} /></div>
            <div>
              <div className="text-[11px] text-slate-400 font-medium">{t.languageLabel}</div>
              <div className="text-xs font-semibold mt-0.5 text-slate-800 capitalize">{language}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};