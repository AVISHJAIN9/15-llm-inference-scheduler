import React, { useEffect, useState } from 'react';

export interface RequestDetail {
  request_id: string;
  model_name: string;
  tenant_id: string;
  priority: number;
  status: string;
  phase?: string;
  prompt_length: number;
  tokens_generated: number;
  max_tokens: number;
  arrival_time: number;
  completion_time?: number;
  elapsed_seconds?: number;
  e2e_duration_ms?: number;
  kv_blocks_allocated: number;
}

interface Props {
  requestId: string;
  onBack?: () => void;
}

export const RequestDetailPage: React.FC<Props> = ({ requestId, onBack }) => {
  const [detail, setDetail] = useState<RequestDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchDetail = async () => {
      try {
        setLoading(true);
        const res = await fetch(`/api/v1/dashboard/requests/${requestId}`);
        if (!res.ok) {
          if (res.status === 404) {
            throw new Error(`Request '${requestId}' not found`);
          }
          throw new Error(`HTTP ${res.status}`);
        }
        const json = await res.json();
        setDetail(json);
        setError(null);
      } catch (err: any) {
        setError(err.message || 'Failed to fetch request detail');
      } finally {
        setLoading(false);
      }
    };
    fetchDetail();
  }, [requestId]);

  return (
    <div id="request-detail-page" className="p-6 bg-slate-900 text-slate-100 rounded-xl shadow-lg border border-slate-800">
      <div className="flex justify-between items-center mb-6">
        <div>
          {onBack && (
            <button
              onClick={onBack}
              aria-label="Back to requests list"
              className="text-xs text-indigo-400 hover:text-indigo-300 mb-1 flex items-center gap-1"
            >
              &larr; Back to Requests
            </button>
          )}
          <h2 className="text-2xl font-bold tracking-tight text-white">Inference Request Inspector (SCH-144)</h2>
          <p className="text-slate-400 text-sm font-mono">{requestId}</p>
        </div>
        {detail && (
          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-indigo-900/40 text-indigo-300 border border-indigo-700">
            {detail.status}
          </span>
        )}
      </div>

      {loading && (
        <div id="detail-loading" className="text-slate-400 py-12 text-center">Loading request details...</div>
      )}

      {error && (
        <div id="detail-error" className="text-red-400 py-4 bg-red-950/30 rounded p-4 border border-red-900">
          {error}
        </div>
      )}

      {detail && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4 bg-slate-800/40 p-5 rounded-lg border border-slate-800">
            <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Request Metadata</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-slate-400">Model Name:</span><span className="font-medium text-white">{detail.model_name}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Tenant ID:</span><span className="font-mono text-slate-300">{detail.tenant_id}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Priority Level:</span><span className="font-medium text-white">{detail.priority}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Prompt Character Count:</span><span className="font-mono text-slate-300">{detail.prompt_length}</span></div>
            </div>
          </div>

          <div className="space-y-4 bg-slate-800/40 p-5 rounded-lg border border-slate-800">
            <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Execution & Memory</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-slate-400">Tokens Generated:</span><span className="font-medium text-white">{detail.tokens_generated} / {detail.max_tokens}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">KV Cache Blocks:</span><span className="font-medium text-sky-400">{detail.kv_blocks_allocated} blocks</span></div>
              {detail.e2e_duration_ms !== undefined && (
                <div className="flex justify-between"><span className="text-slate-400">Total Latency:</span><span className="font-mono text-emerald-400">{detail.e2e_duration_ms} ms</span></div>
              )}
              {detail.elapsed_seconds !== undefined && (
                <div className="flex justify-between"><span className="text-slate-400">Elapsed Time:</span><span className="font-mono text-slate-300">{detail.elapsed_seconds} s</span></div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
