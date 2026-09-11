import Link from 'next/link';
import {
  ArrowRight,
  MessageSquare,
  Sparkles,
  TrendingUp,
  Newspaper,
  TrainTrack,
  Check,
  Database,
  Zap,
} from 'lucide-react';

const promptPills = [
  {
    icon: TrendingUp,
    label: 'Nifty 50 & Stock Quotes',
    query: 'What is the current level and trend of NIFTY 50?',
  },
  {
    icon: TrainTrack,
    label: 'Vande Bharat Status',
    query: 'What is the running status of Vande Bharat Express?',
  },
  {
    icon: Newspaper,
    label: 'Latest Indian News',
    query: 'What are the top news headlines in India today?',
  },
];

const features = [
  {
    icon: TrendingUp,
    title: 'Live Indian Markets',
    description: 'Instant stock prices, indices (NIFTY/SENSEX), and financial metrics fetched directly via real-time market tools.',
    badge: 'MCP Financial Tool',
    color: 'from-violet-500/20 to-purple-500/10 border-violet-500/30',
    iconColor: 'text-violet-400',
  },
  {
    icon: Newspaper,
    title: 'Verified News Crawler',
    description: 'Fresh Indian national, business, and tech headlines indexed algorithmically directly from trusted news sources.',
    badge: 'Live News Tool',
    color: 'from-cyan-500/20 to-blue-500/10 border-cyan-500/30',
    iconColor: 'text-cyan-400',
  },
  {
    icon: TrainTrack,
    title: 'IRCTC Railways Intelligence',
    description: 'Real-time train status, station schedules, and PNR lookup tools integrated into a natural chat interface.',
    badge: 'Railway Tool',
    color: 'from-pink-500/20 to-rose-500/10 border-pink-500/30',
    iconColor: 'text-pink-400',
  },
];

const highlights = [
  { label: 'Architecture', value: 'MCP Tool-Calling' },
  { label: 'Model', value: 'GPT-4o-mini Agent' },
  { label: 'Data Source', value: 'Live Endpoints' },
  { label: 'Hallucinations', value: 'Zero-Memory Guard' },
];

export default function Home() {
  return (
    <main className="min-h-screen pt-24 pb-20 text-slate-200 overflow-x-hidden">
      {/* Hero Section - Unified max-w-5xl grid */}
      <section className="relative px-6 pt-10 pb-12">
        <div className="mx-auto max-w-5xl text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs font-medium text-slate-300 backdrop-blur-xl shadow-sm">
            <Sparkles size={14} className="text-accent animate-pulse" aria-hidden="true" />
            <span>Autonomous Tool-Calling AI Terminal for India</span>
          </div>

          <h1 className="editorial-title mx-auto mt-8 max-w-4xl font-serif text-5xl leading-[1.02] sm:text-7xl md:text-8xl">
            Ask about <br />
            <span className="gradient-text">anything live.</span>
          </h1>

          <p className="mx-auto mt-7 max-w-2xl text-base sm:text-lg leading-8 text-slate-300">
            VoxPath answers from live data — Indian market quotes, verified news headlines, and railway status — by dynamically calling real tools on every request.
          </p>

          {/* Quick Prompt Pills */}
          <div className="mt-8 flex flex-wrap items-center justify-center gap-2.5 max-w-3xl mx-auto" aria-label="Suggested starter prompts">
            {promptPills.map((pill) => {
              const PillIcon = pill.icon;
              return (
                <Link
                  key={pill.label}
                  href={`/chat?q=${encodeURIComponent(pill.query)}`}
                  aria-label={`Ask about ${pill.label}`}
                  className="command-chip flex items-center gap-2 rounded-full px-4 py-2 text-xs font-medium backdrop-blur-md"
                >
                  <PillIcon size={14} className="text-accent" aria-hidden="true" />
                  <span>{pill.label}</span>
                  <ArrowRight size={12} className="opacity-70 group-hover:opacity-100" aria-hidden="true" />
                </Link>
              );
            })}
          </div>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
            <Link
              href="/chat"
              aria-label="Open Chat Terminal"
              className="btn-gradient inline-flex items-center gap-2.5 rounded-full px-8 py-4 text-sm font-semibold shadow-lg"
            >
              <MessageSquare size={18} aria-hidden="true" />
              Open Chat Terminal
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </div>

          {/* Stats bar - Standardized max-w-5xl alignment */}
          <div className="mx-auto mt-14 grid grid-cols-2 sm:grid-cols-4 max-w-5xl gap-4 rounded-2xl border border-white/10 bg-white/5 p-6 backdrop-blur-xl">
            {highlights.map((h) => (
              <div key={h.label} className="text-center p-2">
                <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">{h.label}</div>
                <div className="mt-1.5 text-base sm:text-lg font-bold text-white tracking-tight">{h.value}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Interactive Terminal Preview Showcase - Standardized max-w-5xl alignment */}
      <section className="px-6 py-8" aria-label="Terminal preview demo">
        <div className="mx-auto max-w-5xl">
          <div className="surface-panel rounded-3xl p-6 sm:p-8 shadow-2xl relative overflow-hidden">
            <div className="flex items-center justify-between border-b border-white/10 pb-4 mb-6">
              <div className="flex items-center gap-3">
                <div className="flex gap-1.5" aria-hidden="true">
                  <div className="h-3 w-3 rounded-full bg-rose-500/80" />
                  <div className="h-3 w-3 rounded-full bg-amber-500/80" />
                  <div className="h-3 w-3 rounded-full bg-emerald-500/80" />
                </div>
                <span className="text-xs font-mono text-slate-300">voxpath-intelligence-terminal ~ live</span>
              </div>
              <div className="flex items-center gap-2 text-xs font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-full">
                <Zap size={12} aria-hidden="true" />
                <span>MCP Connected</span>
              </div>
            </div>

            <div className="space-y-4 font-sans text-sm">
              <div className="flex items-start gap-3">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-slate-300 text-xs font-bold" aria-hidden="true">
                  U
                </div>
                <div className="rounded-2xl bg-gradient-to-br from-violet-600 to-indigo-600 px-4 py-2.5 text-white shadow-sm">
                  What is the current trend of NIFTY 50 and key market indices?
                </div>
              </div>

              {/* Resolved static tool call chip - No infinite spinner */}
              <div className="ml-10 flex items-center gap-2 text-xs font-mono text-slate-300 bg-white/5 border border-white/10 rounded-xl px-3.5 py-2 w-fit">
                <Check size={14} className="text-emerald-400" aria-hidden="true" />
                <span>Tool executed: <code className="text-cyan-300">get_stock_price(&quot;NIFTY 50&quot;)</code></span>
              </div>

              <div className="flex items-start gap-3">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-violet-600 to-cyan-500 text-white text-xs font-bold shadow-md" aria-hidden="true">
                  AI
                </div>
                <div className="surface-card rounded-2xl p-4 text-slate-200 border border-white/10 text-sm space-y-2 flex-1">
                  <p className="font-medium text-white">Here is the live market summary:</p>
                  <ul className="list-disc pl-5 space-y-1 text-slate-200 text-xs sm:text-sm">
                    <li><strong className="text-white">NIFTY 50:</strong> 22,450.15 (+0.68%)</li>
                    <li><strong className="text-white">SENSEX:</strong> 73,910.40 (+0.55%)</li>
                    <li><strong className="text-white">Market Sentiment:</strong> Bullish momentum led by Banking and IT indices.</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Capabilities Grid - Standardized max-w-5xl alignment with 2-col tablet step */}
      <section className="px-6 py-12" aria-label="Capabilities grid">
        <div className="mx-auto max-w-5xl">
          <div className="text-center mb-12">
            <h2 className="font-serif text-3xl sm:text-5xl font-bold text-white">
              Real-Time Capabilities
            </h2>
            <p className="mt-4 text-slate-300 max-w-xl mx-auto text-sm sm:text-base">
              Engineered with specialized tools to query live APIs and extract accurate answers instantly.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((f) => {
              const Icon = f.icon;
              return (
                <div
                  key={f.title}
                  className={`surface-card rounded-3xl p-7 border bg-gradient-to-b ${f.color} transition-all duration-300 hover:-translate-y-1`}
                >
                  <div className="flex items-center justify-between mb-5">
                    <div className={`p-3 rounded-2xl bg-white/5 border border-white/10 ${f.iconColor}`}>
                      <Icon size={24} aria-hidden="true" />
                    </div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-300 bg-white/5 border border-white/10 px-3 py-1 rounded-full">
                      {f.badge}
                    </span>
                  </div>
                  <h3 className="text-xl font-bold text-white mb-2.5">{f.title}</h3>
                  <p className="text-sm leading-relaxed text-slate-300">{f.description}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Footer - Standardized max-w-5xl alignment */}
      <footer className="mt-16 border-t border-white/10 px-6 py-8 text-center text-xs text-slate-400">
        <div className="mx-auto max-w-5xl flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Database size={14} className="text-accent" aria-hidden="true" />
            <span className="text-slate-300">VoxPath AI Intelligence Platform</span>
          </div>
          <p className="text-slate-400">© {new Date().getFullYear()} VoxPath. Live data powered by MCP agent tools.</p>
        </div>
      </footer>
    </main>
  );
}
