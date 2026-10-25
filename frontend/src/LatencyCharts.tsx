import React, { useEffect, useState } from 'react';

export interface Percentiles {
  p50: number;
  p90: number;
  p99: number;
}

export interface ModelLatencyMetrics {
  ttft_ms: Percentiles;
  tpot_ms: Percentiles;
  e2e_ms: Percentiles;
}

export interface LatencyChartsResponse {
  timestamp: number;
  metrics: {
    ttft_ms: Record<string, Percentiles>;
    tpot_ms: Record<string, Percentiles>;
    e2e_ms: Record<string, Percentiles>;
  };
}

export const LatencyCharts: React.FC = () => {
  const [data, setData] = useState<LatencyChartsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCharts = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/v1/dashboard/charts/latency');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch latency charts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCharts();
  }, []);

  return (
    <div id="latency-charts-view" className="p-6 bg-slate-900 text-slate-100 rounded-xl shadow-lg border border-slate-800">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white">Latency Distribution Charts (SCH-146)</h2>
          <p className="text-slate-400 text-sm">TTFT, TPOT, and End-to-End latency percentiles across loaded models</p>
        </div>
        <button
          onClick={fetchCharts}
          aria-label="Refresh latency charts"
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium transition"
        >
          Refresh
        </button>
      </div>

      {loading && !data && (
        <div id="latency-loading" className="text-slate-400 py-8 text-center">Loading latency distributions...</div>
      )}

      {error && (
        <div id="latency-error" className="text-red-400 py-4 bg-red-950/30 rounded p-4 border border-red-900 mb-4">
          {error}
        </div>
      )}

      {data && (
        <div className="space-y-6">
          {/* TTFT Section */}
          <div className="bg-slate-800/40 p-5 rounded-lg border border-slate-800">
            <h3 className="text-sm font-semibold text-sky-300 uppercase tracking-wider mb-4">Time To First Token (TTFT)</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(data.metrics.ttft_ms).map(([model, p]) => (
                <div key={model} className="bg-slate-900/60 p-4 rounded border border-slate-800">
                  <div className="font-semibold text-slate-200 mb-2">{model}</div>
                  <div className="flex gap-4 text-xs font-mono">
                    <span className="text-emerald-400">p50: {p.p50}ms</span>
                    <span className="text-amber-400">p90: {p.p90}ms</span>
                    <span className="text-rose-400">p99: {p.p99}ms</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* TPOT Section */}
          <div className="bg-slate-800/40 p-5 rounded-lg border border-slate-800">
            <h3 className="text-sm font-semibold text-emerald-300 uppercase tracking-wider mb-4">Time Per Output Token (TPOT)</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(data.metrics.tpot_ms).map(([model, p]) => (
                <div key={model} className="bg-slate-900/60 p-4 rounded border border-slate-800">
                  <div className="font-semibold text-slate-200 mb-2">{model}</div>
                  <div className="flex gap-4 text-xs font-mono">
                    <span className="text-emerald-400">p50: {p.p50}ms</span>
                    <span className="text-amber-400">p90: {p.p90}ms</span>
                    <span className="text-rose-400">p99: {p.p99}ms</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* E2E Section */}
          <div className="bg-slate-800/40 p-5 rounded-lg border border-slate-800">
            <h3 className="text-sm font-semibold text-indigo-300 uppercase tracking-wider mb-4">End-to-End Latency</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(data.metrics.e2e_ms).map(([model, p]) => (
                <div key={model} className="bg-slate-900/60 p-4 rounded border border-slate-800">
                  <div className="font-semibold text-slate-200 mb-2">{model}</div>
                  <div className="flex gap-4 text-xs font-mono">
                    <span className="text-emerald-400">p50: {p.p50}ms</span>
                    <span className="text-amber-400">p90: {p.p90}ms</span>
                    <span className="text-rose-400">p99: {p.p99}ms</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
