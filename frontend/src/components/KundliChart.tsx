interface Planet {
  name: string;
  sign_name: string;
  isRetro?: string;
}

interface KundliChartProps {
  planets: Planet[];
  ascendantSign: string;
  language: string;
  onHouseClick?: (houseNumber: number) => void;
}

const ZODIAC_SIGNS = [
  'Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
  'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces'
];

const PLANET_ABBR: Record<string, string> = {
  Sun: 'Su', Moon: 'Mo', Mars: 'Ma', Mercury: 'Me', Jupiter: 'Ju',
  Venus: 'Ve', Saturn: 'Sa', Rahu: 'Ra', Ketu: 'Ke',
};

const HOUSE_LABEL_POS: { x: number; y: number }[] = [
  { x: 150, y: 55 }, { x: 70, y: 35 }, { x: 35, y: 70 }, { x: 55, y: 150 },
  { x: 35, y: 230 }, { x: 70, y: 265 }, { x: 150, y: 245 }, { x: 230, y: 265 },
  { x: 265, y: 230 }, { x: 245, y: 150 }, { x: 265, y: 70 }, { x: 230, y: 35 },
];

const STRINGS: Record<string, { title: string; asc: string; centerLabel: string; styleLabel: string }> = {
  English: {
    title: 'Birth Chart (Kundali)',
    asc: 'Asc',
    centerLabel: 'Kundali',
    styleLabel: 'North Indian Style',
  },
  Hindi: {
    title: 'जन्म कुंडली',
    asc: 'लग्न',
    centerLabel: 'कुंडली',
    styleLabel: 'उत्तर भारतीय शैली',
  },
  Hinglish: {
    title: 'Janam Kundali',
    asc: 'Lagna',
    centerLabel: 'Kundali',
    styleLabel: 'North Indian Style',
  },
};

export default function KundliChart({ planets, ascendantSign, language, onHouseClick }: KundliChartProps) {
  const ascIndex = ZODIAC_SIGNS.indexOf(ascendantSign);
  const safeAscIndex = ascIndex === -1 ? 0 : ascIndex;

  const signForHouse = (houseNumber: number): string => {
    const idx = (safeAscIndex + houseNumber - 1) % 12;
    return ZODIAC_SIGNS[idx];
  };

  const planetsByHouse: Record<number, Planet[]> = {};
  for (let house = 1; house <= 12; house++) {
    const sign = signForHouse(house);
    planetsByHouse[house] = planets.filter(
      (p) => p.sign_name?.toLowerCase() === sign.toLowerCase()
    );
  }

  return (
    <div className="w-full bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
        {STRINGS[language]?.title || STRINGS.Hinglish.title}
      </h3>

      <svg viewBox="0 0 300 300" className="w-full h-auto">
        <rect x="10" y="10" width="280" height="280" fill="none" stroke="#cbd5e1" strokeWidth="2" />
        <polygon points="150,10 290,150 150,290 10,150" fill="none" stroke="#cbd5e1" strokeWidth="2" />
        <line x1="10" y1="10" x2="150" y2="150" stroke="#cbd5e1" strokeWidth="2" />
        <line x1="290" y1="10" x2="150" y2="150" stroke="#cbd5e1" strokeWidth="2" />
        <line x1="10" y1="290" x2="150" y2="150" stroke="#cbd5e1" strokeWidth="2" />
        <line x1="290" y1="290" x2="150" y2="150" stroke="#cbd5e1" strokeWidth="2" />

        {HOUSE_LABEL_POS.map((pos, i) => {
          const houseNumber = i + 1;
          const sign = signForHouse(houseNumber);
          const housePlanets = planetsByHouse[houseNumber] || [];

          return (
            <g
              key={houseNumber}
              onClick={() => onHouseClick?.(houseNumber)}
              style={{ cursor: onHouseClick ? 'pointer' : 'default' }}
            >
              {/* invisible hit target so the whole label area is tappable */}
              <circle cx={pos.x} cy={pos.y} r={26} fill="transparent" />
              <text x={pos.x} y={pos.y - 8} textAnchor="middle" fontSize="8" fill="#94a3b8" fontWeight="500">
                {sign.slice(0, 3)}
              </text>
              <text x={pos.x} y={pos.y + 6} textAnchor="middle" fontSize="10" fill="#1e293b" fontWeight="600">
                {housePlanets.map((p) => PLANET_ABBR[p.name] || p.name.slice(0, 2)).join(' ')}
              </text>
              {housePlanets.some((p) => p.isRetro === 'true') && (
                <text x={pos.x} y={pos.y + 18} textAnchor="middle" fontSize="7" fill="#dc2626">
                  (R)
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <p className="mt-3 text-[10px] text-center text-slate-400">
        {STRINGS[language]?.asc || STRINGS.Hinglish.asc}: {ascendantSign} · {STRINGS[language]?.styleLabel || STRINGS.Hinglish.styleLabel}
      </p>
    </div>
  );
}