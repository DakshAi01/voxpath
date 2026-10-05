'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { LogIn, UserPlus, Loader2, AlertCircle } from 'lucide-react';
import { fetchMe, login, register, clearSession, type User } from '@/lib/auth';

/**
 * Shows the chat only to a signed-in user.
 *
 * The check is a real request to /auth/me rather than "is a token present":
 * a token can be expired or signed with a rotated secret, and finding that out
 * at sign-in is far better than mid-conversation.
 */
export function AuthGate({ children }: { children: (user: User, signOut: () => void) => React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchMe()
      .then(setUser)
      .finally(() => setChecking(false));
  }, []);

  const signOut = useCallback(() => {
    clearSession();
    setUser(null);
    setEmail('');
    setPassword('');
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const submitted = mode === 'login' ? await login(email, password) : await register(email, password);
      setUser(submitted);
      setPassword('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  };

  if (checking) {
    return (
      <div className="flex h-[100dvh] items-center justify-center bg-background text-slate-400">
        <Loader2 size={18} className="animate-spin" aria-hidden="true" />
        <span className="ml-2 text-sm">Checking your session…</span>
      </div>
    );
  }

  if (user) return <>{children(user, signOut)}</>;

  const isRegister = mode === 'register';

  return (
    <div className="flex h-[100dvh] items-center justify-center bg-background px-4 font-sans text-slate-200">
      <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-white/[0.03] p-7">
        <h1 className="text-lg font-bold text-white">
          {isRegister ? 'Create your VoxPath account' : 'Sign in to VoxPath'}
        </h1>
        <p className="mt-1 text-xs text-slate-400">
          Your conversations and saved facts are private to your account.
        </p>

        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <div>
            <label htmlFor="email" className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500 focus:border-accent/60"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              autoComplete={isRegister ? 'new-password' : 'current-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500 focus:border-accent/60"
              placeholder={isRegister ? 'At least 8 characters' : '••••••••'}
            />
          </div>

          {error && (
            <p role="alert" className="flex items-start gap-1.5 text-xs text-rose-400">
              <AlertCircle size={13} className="mt-px flex-shrink-0" aria-hidden="true" />
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-black transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {busy ? (
              <Loader2 size={15} className="animate-spin" aria-hidden="true" />
            ) : isRegister ? (
              <UserPlus size={15} aria-hidden="true" />
            ) : (
              <LogIn size={15} aria-hidden="true" />
            )}
            {isRegister ? 'Create account' : 'Sign in'}
          </button>
        </form>

        <button
          type="button"
          onClick={() => {
            setMode(isRegister ? 'login' : 'register');
            setError(null);
          }}
          className="mt-5 w-full text-center text-xs text-slate-400 transition-colors hover:text-slate-200"
        >
          {isRegister ? 'Already have an account? Sign in' : "New here? Create an account"}
        </button>
      </div>
    </div>
  );
}
