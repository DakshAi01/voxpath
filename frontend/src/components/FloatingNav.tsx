'use client';

import Link from 'next/link';
import { Mic, Sparkles, MessageSquare } from 'lucide-react';
import { usePathname } from 'next/navigation';

export const FloatingNav = () => {
  const pathname = usePathname();

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-white/10 bg-[#060611]/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-6">
        <Link
          href="/"
          aria-label="VoxPath Home"
          className="group flex items-center gap-3 transition-transform active:scale-95"
        >
          <div className="orb-core flex h-9 w-9 items-center justify-center rounded-2xl text-white shadow-[var(--shadow-glow)]">
            <Mic size={16} aria-hidden="true" />
          </div>
          <span className="text-lg font-bold tracking-tight text-white">
            Vox<span className="gradient-text">Path</span>
          </span>
        </Link>

        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300 backdrop-blur-md">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <Sparkles size={13} className="text-accent" aria-hidden="true" />
            <span className="font-medium text-[11px] uppercase tracking-wider text-slate-300">Live Data Engine</span>
          </div>

          <nav className="flex items-center gap-1.5" aria-label="Main Navigation">
            <Link
              href="/"
              aria-label="Navigate to Home"
              className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-all ${
                pathname === '/'
                  ? 'bg-white/15 text-white shadow-sm border border-white/10'
                  : 'text-slate-300 hover:bg-white/10 hover:text-white'
              }`}
            >
              Home
            </Link>
            <Link
              href="/chat"
              aria-label="Navigate to Chat Terminal"
              className={`inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-semibold transition-all ${
                pathname === '/chat'
                  ? 'btn-gradient text-white shadow-md'
                  : 'bg-white/10 text-white hover:bg-white/20'
              }`}
            >
              <MessageSquare size={13} aria-hidden="true" />
              Chat Terminal
            </Link>
          </nav>
        </div>
      </div>
    </header>
  );
};
