import React, { useState } from 'react';
import { SchedulerDashboard } from './SchedulerDashboard';
import { QueueDashboard } from './QueueDashboard';
import { LiveRequestView } from './LiveRequestView';
import { RequestDetailPage } from './RequestDetailPage';
import { LatencyCharts } from './LatencyCharts';

export const App: React.FC = () => {
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'live' | 'latency'>('overview');

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-8">
      <header className="max-w-7xl mx-auto mb-8 border-b border-slate-800 pb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-purple-300 to-pink-400">
            LLM Inference Scheduler Ops Console
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Continuous Batching, Paged KV Cache, and Cluster Queue Control
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
          <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">Cluster Online</span>
        </div>
      </header>

      {/* Navigation tabs */}
      <div className="max-w-7xl mx-auto mb-6 flex gap-2 border-b border-slate-800 pb-2">
        <button
          onClick={() => { setActiveTab('overview'); setSelectedRequestId(null); }}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition ${activeTab === 'overview' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'}`}
        >
          Cluster Overview
        </button>
        <button
          onClick={() => { setActiveTab('live'); setSelectedRequestId(null); }}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition ${activeTab === 'live' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'}`}
        >
          Live Requests (SCH-143)
        </button>
        <button
          onClick={() => { setActiveTab('latency'); setSelectedRequestId(null); }}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition ${activeTab === 'latency' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'}`}
        >
          Latency Analytics (SCH-146)
        </button>
      </div>

      <main className="max-w-7xl mx-auto space-y-6">
        {selectedRequestId ? (
          <RequestDetailPage requestId={selectedRequestId} onBack={() => setSelectedRequestId(null)} />
        ) : (
          <>
            {activeTab === 'overview' && (
              <>
                <SchedulerDashboard />
                <QueueDashboard />
              </>
            )}
            {activeTab === 'live' && (
              <LiveRequestView />
            )}
            {activeTab === 'latency' && (
              <LatencyCharts />
            )}
          </>
        )}
      </main>
    </div>
  );
};
