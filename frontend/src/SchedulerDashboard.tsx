import React, { useEffect, useState } from 'react';

export interface SchedulerStats {
  active_batch_size: number;
  max_batch_size: number;
  kv_blocks_used: number;
  kv_blocks_free: number;
  kv_blocks_total: number;
  iteration_count: number;
  queue_depth: number;
  uptime_seconds: number;
}

export const SchedulerDashboard: React.FC = () => {
  const [stats, setStats] = useState<SchedulerStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/v1/dashboard/stats');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setStats(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch scheduler stats');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 2000);
    return () => clearInterval(interval);
  }, []);

  const kvPercent = stats ? Math.round((stats.kv_blocks_used / (stats.kv_blocks_total || 1)) * 100) : 0;

  return (
    <div id="scheduler-dashboard" className="p-6 bg-slate-900 text-slate-100 rounded-xl shadow-lg border border-slate-800">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white">LLM Scheduler Operations Console</h2>
          <p className="text-slate-400 text-sm">Real-time batching throughput and memory telemetry</p>
        </div>
        <button
          onClick={fetchStats}
          aria-label="Refresh scheduler metrics"
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium transition"
        >
          Refresh
        </button>
      </div>

      {loading && !stats && <div id="scheduler-loading" className="text-slate-400 py-8">Loading telemetry...</div>}
      {error && <div id="scheduler-error" className="text-red-400 py-4 bg-red-950/30 rounded p-4 border border-red-900">{error}</div>}

      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-slate-800/60 p-4 rounded-lg border border-slate-700/50">
            <div className="text-slate-400 text-xs font-semibold uppercase tracking-wider">Active Batch</div>
            <div id="metric-batch-size" className="text-3xl font-extrabold text-indigo-400 mt-2">
              {stats.active_batch_size} <span className="text-sm font-normal text-slate-500">/ {stats.max_batch_size}</span>
            </div>
            <div className="text-slate-500 text-xs mt-1">Continuous decode slots</div>
          </div>

          <div className="bg-slate-800/60 p-4 rounded-lg border border-slate-700/50">
            <div className="text-slate-400 text-xs font-semibold uppercase tracking-wider">KV Cache Blocks</div>
            <div id="metric-kv-usage" className="text-3xl font-extrabold text-emerald-400 mt-2">
              {stats.kv_blocks_used} <span className="text-sm font-normal text-slate-500">/ {stats.kv_blocks_total}</span>
            </div>
            <div className="w-full bg-slate-700 h-2 rounded-full mt-2 overflow-hidden">
              <div className="bg-emerald-500 h-full rounded-full transition-all duration-300" style={{ width: `${kvPercent}%` }}></div>
            </div>
          </div>

          <div className="bg-slate-800/60 p-4 rounded-lg border border-slate-700/50">
            <div className="text-slate-400 text-xs font-semibold uppercase tracking-wider">Queue Depth</div>
            <div id="metric-queue-depth" className="text-3xl font-extrabold text-amber-400 mt-2">
              {stats.queue_depth}
            </div>
            <div className="text-slate-500 text-xs mt-1">Pending admission</div>
          </div>

          <div className="bg-slate-800/60 p-4 rounded-lg border border-slate-700/50">
            <div className="text-slate-400 text-xs font-semibold uppercase tracking-wider">Iterations Step</div>
            <div id="metric-iterations" className="text-3xl font-extrabold text-cyan-400 mt-2">
              {stats.iteration_count}
            </div>
            <div className="text-slate-500 text-xs mt-1">Uptime: {stats.uptime_seconds}s</div>
          </div>
        </div>
      )}
    </div>
  );
};
