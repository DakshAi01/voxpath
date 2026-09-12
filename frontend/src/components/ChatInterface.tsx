'use client';

import React, { useEffect, useRef, useState, useCallback, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  Bot,
  SendHorizontal,
  User,
  Sparkles,
  TrendingUp,
  Newspaper,
  TrainTrack,
  Trash2,
  HelpCircle,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

const starterPrompts = [
  {
    icon: TrendingUp,
    title: 'Indian Markets',
    prompt: 'What is the live price, change, and overall trend of NIFTY 50 today?',
    badge: 'Markets',
  },
  {
    icon: Newspaper,
    title: 'Verified Headlines',
    prompt: 'Show me the top latest news headlines in India today.',
    badge: 'News',
  },
  {
    icon: TrainTrack,
    title: 'IRCTC Railways',
    prompt: 'What is the running status of Vande Bharat Express?',
    badge: 'Railways',
  },
  {
    icon: HelpCircle,
    title: 'Market Overview',
    prompt: 'Give me a quick breakdown of major stock market movers in India.',
    badge: 'Analysis',
  },
];

const INITIAL_WELCOME: Message = {
  role: 'assistant',
  content:
    '👋 **VoxPath Terminal Active.** Ask me anything about live Indian stock markets, verified news headlines, or IRCTC railway status.',
};

const MESSAGES_KEY = 'voxpath_chat_messages';
const THREAD_KEY = 'voxpath_thread_id';

/**
 * Mint a conversation id. crypto.randomUUID() needs a secure context, which
 * localhost and https satisfy but a plain-http LAN address does not.
 */
function newThreadId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `t-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function ChatContent() {
  const searchParams = useSearchParams();
  const [messages, setMessages] = useState<Message[]>([INITIAL_WELCOME]);
  const [isThinking, setIsThinking] = useState(false);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [status, setStatus] = useState<'Ready' | 'Processing'>('Ready');
  const [error, setError] = useState<string | null>(null);
  const [draftMessage, setDraftMessage] = useState('');

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isBusy = useRef(false);
  const threadIdRef = useRef<string | null>(null);

  // The thread id identifies this browser's conversation; the transcript itself
  // lives in Postgres behind it. Resolved on first use, not during render.
  const getThreadId = useCallback(() => {
    if (threadIdRef.current) return threadIdRef.current;
    let id: string | null = null;
    try {
      id = localStorage.getItem(THREAD_KEY);
      if (!id) {
        id = newThreadId();
        localStorage.setItem(THREAD_KEY, id);
      }
    } catch {
      // Private mode or blocked storage: fall back to a per-tab thread.
      id = id || newThreadId();
    }
    threadIdRef.current = id;
    return id;
  }, []);

  // Load local storage history on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(MESSAGES_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(parsed);
        }
      }
    } catch {
      // Ignore localStorage errors
    }
  }, []);

  // Save messages to local storage whenever they change
  useEffect(() => {
    if (messages.length > 0) {
      try {
        localStorage.setItem(MESSAGES_KEY, JSON.stringify(messages));
      } catch {
        // Ignore quota/storage errors
      }
    }
  }, [messages]);

  // Check backend health
  const checkHealth = useCallback(async () => {
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000';
      const res = await fetch(`${apiBase}/health`, { signal: AbortSignal.timeout(3000) });
      setBackendOnline(res.ok);
    } catch {
      setBackendOnline(false);
    }
  }, []);

  useEffect(() => {
    void checkHealth();
    const timer = window.setInterval(checkHealth, 6000);
    return () => window.clearInterval(timer);
  }, [checkHealth]);

  // Auto scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isThinking]);

  // Handle URL query parameter if present
  useEffect(() => {
    const query = searchParams.get('q');
    if (query && query.trim()) {
      setDraftMessage(query.trim());
    }
  }, [searchParams]);

  // Auto-resize textarea
  const adjustTextareaHeight = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 140)}px`;
    }
  };

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setDraftMessage(e.target.value);
    adjustTextareaHeight();
  };

  const clearChat = () => {
    setMessages([INITIAL_WELCOME]);
    // Emptying the transcript is not enough: without a fresh thread id the
    // agent still replays the old conversation from Postgres.
    threadIdRef.current = null;
    try {
      localStorage.removeItem(MESSAGES_KEY);
      localStorage.removeItem(THREAD_KEY);
    } catch {
      // Ignore
    }
  };

  const sendTextMessage = async (customPrompt?: string) => {
    const textToSend = (customPrompt || draftMessage).trim();
    if (!textToSend || isBusy.current) return;

    isBusy.current = true;
    setDraftMessage('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    const userMsg: Message = { role: 'user', content: textToSend };
    setMessages((prev) => [...prev, userMsg]);
    setIsThinking(true);
    setStatus('Processing');
    setError(null);

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000';
      const res = await fetch(`${apiBase}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: textToSend,
          thread_id: getThreadId(),
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        const message = typeof data?.error === 'string' ? data.error : 'Backend request failed.';
        throw new Error(message);
      }

      if (data.text) {
        const assistantMsg: Message = { role: 'assistant', content: data.text };
        setMessages((prev) => [...prev, assistantMsg]);
      }
    } catch (backendError) {
      console.error('Backend fetch error:', backendError);
      const msg = backendError instanceof Error ? backendError.message : 'Unable to connect to backend server.';
      setError(msg);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `⚠️ **Connection Error**: ${msg}\n\nMake sure the backend Python service is running on \`http://127.0.0.1:8000\`.`,
        },
      ]);
    } finally {
      isBusy.current = false;
      setIsThinking(false);
      setStatus('Ready');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void sendTextMessage();
    }
  };

  return (
    <div className="relative flex h-[100dvh] w-full flex-col overflow-hidden pt-16 font-sans text-slate-200 bg-background">
      {/* Sub-header status bar */}
      <header className="flex h-12 flex-shrink-0 items-center justify-between border-b border-white/5 bg-white/[0.02] px-6 md:px-10">
        <div className="flex items-center gap-2 text-xs font-semibold text-white">
          <Sparkles size={14} className="text-accent" aria-hidden="true" />
          <span>Intelligence Session</span>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-2.5 py-1">
            <div
              className={cn(
                'h-2 w-2 rounded-full',
                backendOnline === true ? 'bg-emerald-400 animate-pulse' : backendOnline === false ? 'bg-rose-500' : 'bg-amber-400 animate-ping'
              )}
              aria-hidden="true"
            />
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-300">
              {backendOnline === true ? 'Backend Online' : backendOnline === false ? 'Backend Offline' : 'Checking'}
            </span>
          </div>

          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{status}</span>

          {messages.length > 1 && (
            <button
              onClick={clearChat}
              aria-label="Clear conversation history"
              title="Clear Conversation History"
              className="flex items-center gap-1 text-[11px] font-medium text-slate-300 hover:text-rose-400 transition-colors ml-2"
            >
              <Trash2 size={13} aria-hidden="true" />
              <span className="hidden sm:inline">Clear Chat</span>
            </button>
          )}
        </div>
      </header>

      {/* Messages Scroll Area with custom visual scrollbar */}
      <div
        ref={scrollRef}
        aria-live="polite"
        aria-label="Chat messages transcript"
        className="mx-auto w-full max-w-3xl flex-1 space-y-6 overflow-y-auto px-4 sm:px-6 py-6 custom-scrollbar"
      >
        {messages.map((msg, i) => (
          <div
            key={i}
            className={cn('flex animate-fade-in gap-3.5', msg.role === 'user' ? 'flex-row-reverse' : 'flex-row')}
          >
            <div
              className={cn(
                'mt-1 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl text-xs shadow-md',
                msg.role === 'assistant'
                  ? 'bg-gradient-to-br from-violet-600 to-cyan-500 text-white'
                  : 'border border-white/10 bg-white/10 text-slate-200'
              )}
              aria-hidden="true"
            >
              {msg.role === 'assistant' ? <Bot size={16} /> : <User size={16} />}
            </div>

            <div
              className={cn(
                'max-w-[85%] rounded-2xl px-5 py-3.5 text-sm leading-relaxed shadow-sm',
                msg.role === 'assistant'
                  ? 'surface-card text-slate-100 border border-white/10'
                  : 'bg-gradient-to-br from-violet-600/90 to-indigo-600/90 text-white'
              )}
            >
              {msg.role === 'assistant' ? (
                <div className="prose prose-invert max-w-none text-sm leading-relaxed prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 prose-headings:text-white prose-headings:font-bold prose-strong:text-white prose-code:text-cyan-300 prose-code:bg-white/10 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-a:text-cyan-400">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              ) : (
                <p className="whitespace-pre-wrap">{msg.content}</p>
              )}
            </div>
          </div>
        ))}

        {/* Starter Suggestion Cards when only welcome message exists */}
        {messages.length <= 1 && (
          <div className="mt-8 space-y-4 animate-fade-in" aria-label="Suggested starter queries">
            <div className="text-center text-xs font-semibold uppercase tracking-wider text-slate-400">
              Suggested Starter Queries
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {starterPrompts.map((sp) => {
                const Icon = sp.icon;
                return (
                  <button
                    key={sp.title}
                    onClick={() => void sendTextMessage(sp.prompt)}
                    aria-label={`Ask: ${sp.prompt}`}
                    className="command-chip flex flex-col items-start p-4 rounded-2xl text-left border border-white/10 bg-white/5 hover:bg-white/10 hover:border-white/20 transition-all group"
                  >
                    <div className="flex items-center justify-between w-full mb-2">
                      <div className="flex items-center gap-2 text-xs font-bold text-white">
                        <Icon size={15} className="text-accent" aria-hidden="true" />
                        <span>{sp.title}</span>
                      </div>
                      <span className="text-[10px] font-semibold text-slate-300 bg-white/5 border border-white/10 px-2 py-0.5 rounded-full">
                        {sp.badge}
                      </span>
                    </div>
                    <p className="text-xs text-slate-300 group-hover:text-white line-clamp-2">{sp.prompt}</p>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {isThinking && (
          <div className="flex animate-pulse items-center gap-3 pl-11" aria-label="Assistant thinking">
            <div className="flex gap-1.5" aria-hidden="true">
              <div className="h-2 w-2 rounded-full bg-accent" />
              <div className="h-2 w-2 rounded-full bg-accent opacity-60" />
              <div className="h-2 w-2 rounded-full bg-accent opacity-30" />
            </div>
            <span className="text-[10px] font-bold uppercase tracking-[0.25em] text-accent/90">
              Executing Agent Tools...
            </span>
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="flex-shrink-0 px-4 sm:px-6 pb-6 pt-2">
        <div className="surface-card glow relative mx-auto max-w-3xl rounded-2xl border border-white/15 p-2 bg-[#0c0c1c]/90">
          {error && (
            <div className="absolute -top-11 left-0 right-0 text-center">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-rose-500/30 bg-rose-950/80 px-4 py-1.5 text-xs font-semibold text-rose-300 backdrop-blur-md shadow-lg">
                <AlertCircle size={13} aria-hidden="true" />
                {error}
              </span>
            </div>
          )}

          <form
            className="flex items-end gap-3 px-3 py-1.5"
            onSubmit={(e) => {
              e.preventDefault();
              void sendTextMessage();
            }}
          >
            <Sparkles size={18} className="mb-3 text-slate-400 transition-colors group-focus-within:text-accent" aria-hidden="true" />

            <textarea
              ref={textareaRef}
              rows={1}
              value={draftMessage}
              onChange={handleTextChange}
              onKeyDown={handleKeyDown}
              aria-label="Type your message prompt"
              placeholder="Ask about Indian stock quotes, railway status, or news headlines... (Shift+Enter for newline)"
              className="flex-1 resize-none border-none bg-transparent text-sm font-medium text-slate-100 outline-none placeholder:text-slate-400 py-1.5 max-h-36 custom-scrollbar"
            />

            <button
              type="submit"
              aria-label="Send prompt"
              disabled={!draftMessage.trim() || isThinking || isBusy.current}
              className="btn-gradient flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl disabled:opacity-30 disabled:grayscale transition-transform active:scale-95"
            >
              <SendHorizontal size={17} aria-hidden="true" />
            </button>
          </form>
        </div>
        <div className="mt-2 text-center text-[11px] text-slate-400">
          VoxPath calls live tools for Indian markets, IRCTC, and news. Powered by MCP Agent.
        </div>
      </div>
    </div>
  );
}

export const ChatInterface = () => {
  return (
    <Suspense
      fallback={
        <div className="flex h-[100dvh] w-full items-center justify-center text-slate-300 gap-2">
          <RefreshCw size={18} className="animate-spin text-accent" aria-hidden="true" />
          <span>Loading Terminal Interface...</span>
        </div>
      }
    >
      <ChatContent />
    </Suspense>
  );
};
