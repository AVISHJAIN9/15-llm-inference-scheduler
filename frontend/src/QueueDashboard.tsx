import React, { useEffect, useState } from 'react';

export interface QueuedRequestItem {
  request_id: str;
  model_name: str;
  priority: number;
  max_tokens: number;
  arrival_time: number;
  status: str;
}

export interface QueueData {
  queue_depth: number;
  max_capacity: number;
  queued_items: QueuedRequestItem[];
}

export const QueueDashboard: React.FC = () => {
  const [data, setData] = useState<QueueData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchQueue = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/v1/dashboard/queue');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load queue data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQueue();
    const interval = setInterval(fetchQueue, 2000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div id="queue-dashboard" className="p-6 bg-slate-900 text-slate-100 rounded-xl shadow-lg border border-slate-800 mt-6">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h3 className="text-xl font-bold text-white">Pending Requests Queue</h3>
          <p className="text-slate-400 text-sm">
            Capacity: {data?.queue_depth || 0} / {data?.max_capacity || 1000} items
          </p>
        </div>
        <button
          onClick={fetchQueue}
          aria-label="Refresh queue items"
          className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-md text-xs font-medium transition"
        >
          Refresh Queue
        </button>
      </div>

      {loading && !data && <div id="queue-loading" className="text-slate-400 py-4">Inspecting queue...</div>}
      {error && <div id="queue-error" className="text-red-400 py-2">{error}</div>}

      {data && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 text-xs uppercase tracking-wider">
                <th className="py-3 px-4">Request ID</th>
                <th className="py-3 px-4">Model</th>
                <th className="py-3 px-4">Priority</th>
                <th className="py-3 px-4">Max Tokens</th>
                <th className="py-3 px-4">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {data.queued_items.length === 0 ? (
                <tr>
                  <td colSpan={5} id="queue-empty-state" className="py-8 text-center text-slate-500 italic">
                    Queue is empty. No pending inference requests.
                  </td>
                </tr>
              ) : (
                data.queued_items.map((item) => (
                  <tr key={item.request_id} className="hover:bg-slate-800/40 transition">
                    <td className="py-3 px-4 font-mono text-xs text-indigo-300">{item.request_id}</td>
                    <td className="py-3 px-4 text-slate-300">{item.model_name}</td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                        P{item.priority}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-400">{item.max_tokens}</td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded text-xs bg-slate-800 text-slate-300 border border-slate-700">
                        {item.status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
