import { useState } from 'react';
import KundliChart from './KundliChart';
import SouthIndianChart from './SouthIndianChart';
import HouseInsightPanel from './HouseInsightPanel';

interface Planet {
  name: string;
  sign_name: string;
  isRetro?: string;
}

interface KundliChartToggleProps {
  planets: Planet[];
  ascendantSign: string;
  language: string;
  sessionId: string;
}

const STRINGS: Record<string, { north: string; south: string; ascendant: string; title: string }> = {
  English: {
    north: 'North Indian',
    south: 'South Indian',
    ascendant: 'Ascendant',
    title: 'Birth Chart (Kundali)',
  },
  Hindi: {
    north: 'उत्तर भारतीय',
    south: 'दक्षिण भारतीय',
    ascendant: 'लग्न',
    title: 'जन्म कुंडली',
  },
  Hinglish: {
    north: 'North Indian',
    south: 'South Indian',
    ascendant: 'Lagna',
    title: 'Janam Kundali',
  },
};

export default function KundliChartToggle({ planets, ascendantSign, language, sessionId }: KundliChartToggleProps) {
  const [style, setStyle] = useState<'north' | 'south'>('north');
  const [selectedHouse, setSelectedHouse] = useState<number | null>(null);
  const t = STRINGS[language] || STRINGS.Hinglish;

  return (
    <div>
      <div className="flex justify-center gap-2 mb-3">
        <button
          onClick={() => setStyle('north')}
          className={`px-3 py-1.5 rounded-full text-xs font-medium transition ${
            style === 'north'
              ? 'bg-slate-900 text-white'
              : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
          }`}
        >
          {t.north}
        </button>
        <button
          onClick={() => setStyle('south')}
          className={`px-3 py-1.5 rounded-full text-xs font-medium transition ${
            style === 'south'
              ? 'bg-slate-900 text-white'
              : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
          }`}
        >
          {t.south}
        </button>
      </div>

      {style === 'north' ? (
        <KundliChart
          planets={planets}
          ascendantSign={ascendantSign}
          language={language}
          onHouseClick={setSelectedHouse}
        />
      ) : (
        <SouthIndianChart
          planets={planets}
          ascendantSign={ascendantSign}
          language={language}
          onHouseClick={setSelectedHouse}
        />
      )}

      <HouseInsightPanel
        sessionId={sessionId}
        houseNumber={selectedHouse}
        language={language}
        onClose={() => setSelectedHouse(null)}
      />
    </div>
  );
}