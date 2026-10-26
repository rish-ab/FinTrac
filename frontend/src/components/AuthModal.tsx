import { useState, type FormEvent } from 'react';
import { Activity, ArrowRight, Eye, EyeOff, LoaderCircle, X } from 'lucide-react';
import { ApiError, api } from '../api/client';
import { setAccessToken } from '../api/token-store';
import type { UserResponse } from '../api/types';

interface AuthModalProps { onClose: () => void; onAuthenticated: (user: UserResponse) => void; }

type AuthMode = 'login' | 'register';

export default function AuthModal({ onClose, onAuthenticated }: AuthModalProps) {
  const [mode, setMode] = useState<AuthMode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true); setError(null); setSuccess(null);
    try {
      if (mode === 'register') {
        await api.register({ email: email.trim(), password });
        setSuccess('Account created. Sign in with your new credentials.');
        setMode('login');
        setPassword('');
        return;
      }
      const response = await api.login(email.trim(), password);
      setAccessToken(response.access_token, response.user);
      onAuthenticated(response.user);
      onClose();
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 0) setError('Could not connect to the API. Check the API origin and try again.');
      else setError(reason instanceof Error ? reason.message : 'Authentication failed.');
    } finally {
      setLoading(false);
    }
  }

  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-canvas"><Activity size={21} /></div><div><p className="text-xs uppercase tracking-[.15em] text-mutedText">FinTrac V3</p><h2 id="auth-title" className="mt-1 text-lg font-semibold text-primaryText">{mode === 'login' ? 'Sign in to your workspace' : 'Create an account'}</h2></div></div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close sign in dialog"><X size={16} /></button>
      </div>
      <p className="mt-3 text-sm leading-6 text-secondaryText">{mode === 'login' ? 'Access your portfolios and personalized watchlist.' : 'Register using the API-supported email and password fields.'}</p>
      <div className="mt-5 grid grid-cols-2 rounded-lg border border-line bg-canvas p-1">
        <button type="button" onClick={() => { setMode('login'); setError(null); setSuccess(null); }} className={`rounded-md px-3 py-2 text-sm ${mode === 'login' ? 'bg-raised font-medium text-primaryText' : 'text-secondaryText'}`}>Sign in</button>
        <button type="button" onClick={() => { setMode('register'); setError(null); setSuccess(null); }} className={`rounded-md px-3 py-2 text-sm ${mode === 'register' ? 'bg-raised font-medium text-primaryText' : 'text-secondaryText'}`}>Register</button>
      </div>
      <form className="mt-5 space-y-4" onSubmit={submit}>
        <label className="form-label">Email address<input className="input-control mt-2" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required maxLength={254} placeholder="you@company.com" /></label>
        <label className="form-label">Password<div className="relative mt-2"><input className="input-control pr-11" type={showPassword ? 'text' : 'password'} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={(event) => setPassword(event.target.value)} required minLength={1} placeholder="Enter password" /><button type="button" className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-2 text-mutedText hover:text-primaryText" aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword((value) => !value)}>{showPassword ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></label>
        {error && <div className="rounded-md border border-loss/30 bg-loss/10 px-3 py-2 text-sm text-loss" role="alert">{error}</div>}
        {success && <div className="rounded-md border border-gain/30 bg-gain/10 px-3 py-2 text-sm text-gain" role="status">{success}</div>}
        <button type="submit" className="button-primary w-full justify-center" disabled={loading}>{loading ? <LoaderCircle size={16} className="animate-spin" /> : <ArrowRight size={16} />}{loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
      </form>
      <p className="mt-4 text-center text-[11px] leading-5 text-mutedText">Authentication uses the supplied FastAPI OAuth2 password flow. Your password is submitted to the API and is not stored by this frontend.</p>
    </section>
  </div>;
}
