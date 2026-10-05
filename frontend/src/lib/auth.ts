/**
 * Session handling for VoxPath.
 *
 * The token is the only thing that proves who the caller is; the backend never
 * accepts a user id from the request body. Kept in localStorage, which is
 * per-browser and survives reloads but is readable by any script on this
 * origin — acceptable for a single-origin app, and the reason the token has a
 * limited lifetime rather than being permanent.
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000';

const TOKEN_KEY = 'voxpath_token';

export type User = { id: string; email: string };

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null; // private mode or blocked storage
  }
}

function setToken(token: string) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Storage unavailable: the session lasts until reload rather than failing.
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    // The thread belongs to the account that created it, so a new sign-in
    // must not inherit it. The transcript goes too.
    localStorage.removeItem('voxpath_thread_id');
    localStorage.removeItem('voxpath_chat_messages');
  } catch {
    // Ignore
  }
}

/** Read the API's error message, which is clearer than a status code. */
async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === 'string') return detail;
    // FastAPI validation errors arrive as a list of field problems.
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
    if (typeof body?.error === 'string') return body.error;
  } catch {
    // Not JSON; fall through.
  }
  return fallback;
}

async function submit(path: string, email: string, password: string): Promise<User> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await errorMessage(res, 'Could not sign in.'));
  const data = await res.json();
  setToken(data.access_token);
  return data.user as User;
}

export const login = (email: string, password: string) => submit('/auth/login', email, password);
export const register = (email: string, password: string) => submit('/auth/register', email, password);

/** The signed-in user, or null when there is no valid session. */
export async function fetchMe(): Promise<User | null> {
  const token = getToken();
  if (!token) return null;
  try {
    const res = await fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(5000),
    });
    if (res.status === 401) {
      clearSession(); // expired or revoked
      return null;
    }
    if (!res.ok) return null;
    return (await res.json()) as User;
  } catch {
    return null; // backend unreachable; treated as signed out
  }
}

/** fetch with the session token attached. */
export function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  return fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
}
