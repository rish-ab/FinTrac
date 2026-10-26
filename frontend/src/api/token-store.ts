const TOKEN_KEY = 'fintrac.access_token';
const USER_KEY = 'fintrac.user';

export function getAccessToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAccessToken(token: string, user?: unknown): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
    if (user !== undefined) window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    // Storage may be unavailable in restrictive browsing contexts.
  }
}

export function clearAccessToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  } catch {
    // Storage may be unavailable in restrictive browsing contexts.
  }
}

export function getStoredUser<T>(): T | null {
  try {
    const value = window.localStorage.getItem(USER_KEY);
    return value ? (JSON.parse(value) as T) : null;
  } catch {
    return null;
  }
}
