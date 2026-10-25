import React, { useEffect, useState } from 'react';

export interface LiveRequestItem {
  request_id: string;
  model_name: string;
  tenant_id: string;
  priority: number;
  tokens_generated: number;
  max_tokens: number;
  phase: string;
  arrival_time: number;
  elapsed_seconds: number;
  status: string;
}

export interface LiveRequestsResponse {
  active_count: number;
  max_batch_size: number;
  requests: LiveRequestItem[];
}

export const LiveRequestView: React.FC = () => {
  const [data, setData] = useState<LiveRequestsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchLive = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/v1/dashboard/requests/live');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch live requests');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLive();
    const timer = setInterval(fetchLive, 3000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div id="live-requests-view" className="p-6 bg-slate-900 text-slate-100 rounded-xl shadow-lg border border-slate-800">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white">Live In-Flight Requests (SCH-143)</h2>
          <p className="text-slate-400 text-sm">Real-time iteration tracking of continuous batch execution</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-400">
            Batch Occupancy: <strong className="text-indigo-400">{data?.active_count || 0}</strong> / {data?.max_batch_size || 0}
          </span>
          <button
            onClick={fetchLive}
            aria-label="Refresh live requests"
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium transition"
          >
            Refresh
          </button>
        </div>
      </div>

      {loading && !data && (
        <div id="live-loading" className="text-slate-400 py-8 text-center">Loading live requests...</div>
      )}

      {error && (
        <div id="live-error" className="text-red-400 py-4 bg-red-950/30 rounded p-4 border border-red-900 mb-4">
          {error}
        </div>
      )}

      {data && data.requests.length === 0 && (
        <div id="live-empty" className="text-slate-500 py-12 text-center bg-slate-800/40 rounded-lg border border-slate-800">
          No inference requests currently in flight.
        </div>
      )}

      {data && data.requests.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm border-collapse" aria-label="Active Requests Table">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 uppercase text-xs">
                <th className="py-3 px-4">Request ID</th>
                <th className="py-3 px-4">Model</th>
                <th className="py-3 px-4">Tenant</th>
                <th className="py-3 px-4">Priority</th>
                <th className="py-3 px-4">Phase</th>
                <th className="py-3 px-4">Tokens</th>
                <th className="py-3 px-4">Elapsed</th>
                <th className="py-3 px-4">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {data.requests.map((req) => (
                <tr key={req.request_id} className="hover:bg-slate-800/50 transition">
                  <td className="py-3 px-4 font-mono font-medium text-indigo-300">{req.request_id}</td>
                  <td className="py-3 px-4">{req.model_name}</td>
                  <td className="py-3 px-4 text-slate-400">{req.tenant_id}</td>
                  <td className="py-3 px-4">{req.priority}</td>
                  <td className="py-3 px-4">
                    <span className="px-2 py-0.5 rounded text-xs bg-sky-900/40 text-sky-300 border border-sky-800">
                      {req.phase}
                    </span>
                  </td>
                  <td className="py-3 px-4">{req.tokens_generated} / {req.max_tokens}</td>
                  <td className="py-3 px-4">{req.elapsed_seconds}s</td>
                  <td className="py-3 px-4">
                    <span className="px-2 py-0.5 rounded text-xs bg-emerald-900/40 text-emerald-300 border border-emerald-800">
                      {req.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
