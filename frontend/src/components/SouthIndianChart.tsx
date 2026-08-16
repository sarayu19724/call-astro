
interface Planet {
  name: string;
  sign_name: string;
  isRetro?: string;
}

interface SouthIndianChartProps {
  planets: Planet[];
  ascendantSign: string;
  language: string;
}

const PLANET_ABBR: Record<string, string> = {
  Sun: 'Su', Moon: 'Mo', Mars: 'Ma', Mercury: 'Me', Jupiter: 'Ju',
  Venus: 'Ve', Saturn: 'Sa', Rahu: 'Ra', Ketu: 'Ke',
};

const GRID_SIGNS: (string | null)[][] = [
  ['Pisces', 'Aries', 'Taurus', 'Gemini'],
  ['Aquarius', null, null, 'Cancer'],
  ['Capricorn', null, null, 'Leo'],
  ['Sagittarius', 'Scorpio', 'Libra', 'Virgo'],
];

const STRINGS: Record<string, { title: string; asc: string; centerLabel: string; styleLabel: string }> = {
  English: {
    title: 'Birth Chart (Kundali)',
    asc: 'Asc',
    centerLabel: 'Kundali',
    styleLabel: 'South Indian Style',
  },
  Hindi: {
    title: 'जन्म कुंडली',
    asc: 'लग्न',
    centerLabel: 'कुंडली',
    styleLabel: 'दक्षिण भारतीय शैली',
  },
  Hinglish: {
    title: 'Janam Kundali',
    asc: 'Lagna',
    centerLabel: 'Kundali',
    styleLabel: 'South Indian Style',
  },
};

export default function SouthIndianChart({ planets, ascendantSign, language }: SouthIndianChartProps) {
  const t = STRINGS[language] || STRINGS.Hinglish;

  const planetsForSign = (sign: string): Planet[] =>
    planets.filter((p) => p.sign_name?.toLowerCase() === sign.toLowerCase());

  return (
    <div className="w-full bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
        {t.title}
      </h3>

      <div className="grid grid-cols-4 grid-rows-4 border border-slate-300 aspect-square">
        {GRID_SIGNS.flat().map((sign, i) => {
          if (sign === null) {
            return i === 5 ? (
              <div
                key="center"
                className="col-start-2 col-span-2 row-start-2 row-span-2 flex items-center justify-center border border-slate-200 bg-slate-50"
              >
                <span className="text-[10px] text-slate-300">{t.centerLabel}</span>
              </div>
            ) : null;
          }

          const cellPlanets = planetsForSign(sign);
          const isAscendant = sign.toLowerCase() === ascendantSign?.toLowerCase();

          return (
            <div
              key={sign}
              className="border border-slate-200 flex flex-col items-center justify-center p-1 relative"
            >
              <span className="text-[8px] text-slate-400 absolute top-1 left-1">
                {sign.slice(0, 3)}
              </span>
              {isAscendant && (
                <span className="text-[8px] text-indigo-500 font-bold absolute top-1 right-1">
                  {t.asc}
                </span>
              )}
              <span className="text-[10px] font-semibold text-slate-800 mt-2 text-center leading-tight">
                {cellPlanets.map((p) => PLANET_ABBR[p.name] || p.name.slice(0, 2)).join(' ')}
              </span>
              {cellPlanets.some((p) => p.isRetro === 'true') && (
                <span className="text-[7px] text-rose-500">(R)</span>
              )}
            </div>
          );
        })}
      </div>

      <p className="mt-3 text-[10px] text-center text-slate-400">
        {t.asc}: {ascendantSign} · {t.styleLabel}
      </p>
    </div>
  );
}