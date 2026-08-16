interface QuickTopicsProps {
  onSelect: (topic: string) => void;
  disabled?: boolean;
  language: string;
}

const TOPICS: Record<string, { label: string; message: string }[]> = {
  English: [
    { label: 'Career 💼', message: 'How will my career go?' },
    { label: 'Marriage 💍', message: 'Tell me about my marriage.' },
    { label: 'Finance 💰', message: 'How is my financial future?' },
    { label: 'Kundli 🪐', message: 'Tell me about my Kundli.' },
    { label: 'Health 🩺', message: 'How will my health be?' },
    { label: 'Planets ✨', message: 'What is the position of my planets?' },
  ],
  Hindi: [
    { label: 'करियर 💼', message: 'मेरा करियर कैसा रहेगा?' },
    { label: 'शादी 💍', message: 'मेरी शादी के बारे में बताइए।' },
    { label: 'वित्त 💰', message: 'मेरा वित्तीय भविष्य कैसा है?' },
    { label: 'कुंडली 🪐', message: 'मेरी कुंडली के बारे में बताइए।' },
    { label: 'स्वास्थ्य 🩺', message: 'मेरा स्वास्थ्य कैसा रहेगा?' },
    { label: 'ग्रह ✨', message: 'मेरे ग्रहों की स्थिति क्या है?' },
  ],
  Hinglish: [
    { label: 'Career 💼', message: 'Mera career kaisa rahega?' },
    { label: 'Marriage 💍', message: 'Meri shaadi ke baare mein bataiye.' },
    { label: 'Finance 💰', message: 'Mera financial future kaisa hai?' },
    { label: 'Kundli 🪐', message: 'Meri kundli ke baare mein bataiye.' },
    { label: 'Health 🩺', message: 'Meri health kaisi rahegi?' },
    { label: 'Planets ✨', message: 'Mere grahon ki sthiti kya hai?' },
  ],
};

export default function QuickTopics({ onSelect, disabled, language }: QuickTopicsProps) {
  const topics = TOPICS[language] || TOPICS.Hinglish;

  return (
    <div className="flex flex-wrap gap-2 px-4 pt-3 pb-1 border-t border-slate-100 bg-white">
      {topics.map((topic) => (
        <button
          key={topic.label}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(topic.message)}
          className="text-xs font-medium px-3 py-1.5 rounded-full border border-slate-200 text-slate-600 bg-slate-50 hover:bg-slate-100 hover:border-slate-300 transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {topic.label}
        </button>
      ))}
    </div>
  );
}