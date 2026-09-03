import { useState } from 'react';
import { FileText, Loader2 } from 'lucide-react';

const API_BASE =
  ((import.meta as ImportMeta & { env?: { VITE_API_BASE?: string } }).env?.VITE_API_BASE) || '/api';

interface KundliReportButtonProps {
  sessionId: string;
  language: string;
  name: string | null;
}

const LABELS: Record<string, { button: string; error: string }> = {
  English: { button: 'Download Kundli PDF', error: "Couldn't generate the report. Please try again." },
  Hindi: { button: 'कुंडली PDF डाउनलोड करें', error: 'रिपोर्ट नहीं बन सकी। कृपया दोबारा प्रयास करें।' },
  Hinglish: { button: 'Kundli PDF Download Karein', error: 'Report nahi ban saki. Kripya dobara koshish karein.' },
};

export default function KundliReportButton({ sessionId, language, name }: KundliReportButtonProps) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const t = LABELS[language] || LABELS.Hinglish;

  const handleDownload = async () => {
    setDownloading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/kundli-report?language=${encodeURIComponent(language)}`);
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || 'Failed to generate report');
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(name || 'Kundli').replace(/\s+/g, '_')}_Kundli_${language}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      console.error('Report download failed:', err);
      setError(t.error);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="flex flex-col items-end">
      <button
        onClick={handleDownload}
        disabled={downloading}
        className="flex items-center gap-1.5 text-xs font-semibold text-white bg-amber-500 hover:bg-amber-600 disabled:opacity-60 px-3 py-2 rounded-lg shadow-sm transition"
      >
        {downloading ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />}
        {t.button}
      </button>
      {error && <span className="text-[10px] text-rose-500 mt-1">{error}</span>}
    </div>
  );
}