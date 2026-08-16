import { ArrowRight } from 'lucide-react';

interface GoToChatCardProps {
  language: string;
  onGoToChat: () => void;
}

const STRINGS: Record<string, { title: string; subtitle: string }> = {
  English: {
    title: 'Go to Chat',
    subtitle: 'Ask questions, get insights, and explore your chart',
  },
  Hindi: {
    title: 'चैट पर जाएं',
    subtitle: 'सवाल पूछें, जानकारी पाएं और अपनी कुंडली को समझें',
  },
  Hinglish: {
    title: 'Chat Par Jaayein',
    subtitle: 'Sawal puchiye, insights paayein aur apni kundli explore karein',
  },
};

export default function GoToChatCard({ language, onGoToChat }: GoToChatCardProps) {
  const t = STRINGS[language] || STRINGS.Hinglish;

  return (
    <button
      onClick={onGoToChat}
      className="w-full bg-amber-500 hover:bg-amber-600 rounded-2xl px-8 py-6 shadow-sm transition flex items-center justify-between text-left"
    >
      <div>
        <h3 className="text-white font-semibold text-base">{t.title}</h3>
        <p className="text-amber-50 text-sm mt-0.5">{t.subtitle}</p>
      </div>
      <ArrowRight size={22} className="text-white shrink-0" />
    </button>
  );
}