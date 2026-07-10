import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useFirebaseConfig } from '../context/FirebaseConfigContext';
import { Mail, Lock, User as UserIcon, LogIn, ArrowRight, ShieldCheck, Settings } from 'lucide-react';

export const AuthScreen: React.FC = () => {
  const { loginAnonymously, loginWithEmail, registerWithEmail } = useAuth();
  const { clearConfig } = useFirebaseConfig();
  const [tab, setTab] = useState<'signin' | 'signup' | 'anonymous'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (tab === 'signin') {
        if (!email || !password) throw new Error('Please fill in all fields');
        await loginWithEmail(email, password);
      } else if (tab === 'signup') {
        if (!email || !password || !displayName) throw new Error('Please fill in all fields');
        if (password.length < 6) throw new Error('Password must be at least 6 characters');
        await registerWithEmail(email, password, displayName);
      } else {
        await loginAnonymously();
      }
    } catch (err: any) {
      console.error(err);
      setError(err.message || 'An error occurred during authentication.');
      setLoading(false);
    }
  };

  const handleAnonymousSubmit = async () => {
    setError(null);
    setLoading(true);
    try {
      await loginAnonymously();
    } catch (err: any) {
      console.error(err);
      setError(err.message || 'Could not sign in anonymously.');
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-radial from-slate-900 to-black p-4">
      {/* Background Glows */}
      <div className="absolute top-1/4 left-1/4 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-indigo-500/10 blur-3xl rounded-full pointer-events-none animate-pulse-slow"></div>
      <div className="absolute bottom-1/4 right-1/4 translate-x-1/2 translate-y-1/2 w-96 h-96 bg-fuchsia-500/10 blur-3xl rounded-full pointer-events-none animate-pulse-slow"></div>

      {/* Settings / Reset Firebase Config trigger */}
      <button 
        onClick={clearConfig} 
        title="Reset Firebase Settings"
        className="absolute top-4 right-4 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/5 bg-slate-900/50 hover:bg-slate-900/90 text-slate-400 hover:text-white transition-all text-xs cursor-pointer"
      >
        <Settings size={14} /> Reset Firebase Config
      </button>

      <div className="w-full max-w-md glass rounded-2xl p-6 md:p-8 shadow-2xl relative overflow-hidden">
        
        {/* Decorative Top Accent Line */}
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-indigo-500 to-fuchsia-500"></div>

        {/* Branding header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-gradient-to-tr from-indigo-500 to-fuchsia-500 text-white font-black text-2xl shadow-lg shadow-indigo-500/20 mb-4 animate-float">
            ✨
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-white mb-2">AMDChat</h1>
          <p className="text-slate-400 text-sm">Elevate your conversations in real-time</p>
        </div>

        {/* Tabs switcher */}
        <div className="flex border-b border-white/5 mb-6 p-1 bg-slate-950/40 rounded-xl">
          <button
            onClick={() => { setTab('signin'); setError(null); }}
            className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
              tab === 'signin' 
                ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/10' 
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            Sign In
          </button>
          <button
            onClick={() => { setTab('signup'); setError(null); }}
            className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
              tab === 'signup' 
                ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/10' 
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            Create Account
          </button>
          <button
            onClick={() => { setTab('anonymous'); setError(null); }}
            className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
              tab === 'anonymous' 
                ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/10' 
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            Anonymous
          </button>
        </div>

        {error && (
          <div className="p-3 text-xs bg-rose-500/10 border border-rose-500/20 text-rose-300 rounded-lg mb-4 animate-shake">
            {error}
          </div>
        )}

        {tab !== 'anonymous' ? (
          <form onSubmit={handleSubmit} className="space-y-4">
            {tab === 'signup' && (
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Display Name</label>
                <div className="relative">
                  <UserIcon className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
                  <input
                    type="text"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="Enter display name"
                    className="w-full text-sm pl-10 pr-4 py-2.5 rounded-lg border border-white/10 bg-slate-950/40 text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/50"
                    required
                  />
                </div>
              </div>
            )}

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Email Address</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  className="w-full text-sm pl-10 pr-4 py-2.5 rounded-lg border border-white/10 bg-slate-950/40 text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/50"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full text-sm pl-10 pr-4 py-2.5 rounded-lg border border-white/10 bg-slate-950/40 text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/50"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-lg bg-gradient-to-r from-indigo-500 to-fuchsia-500 text-white font-medium text-sm flex items-center justify-center gap-2 hover:opacity-90 active:scale-[0.98] transition-all disabled:opacity-50 shadow-lg shadow-indigo-500/10 cursor-pointer"
            >
              {loading ? (
                <div className="w-5 h-5 rounded-full border-2 border-white/30 border-t-white animate-spin"></div>
              ) : tab === 'signin' ? (
                <>
                  <LogIn size={16} /> Sign In
                </>
              ) : (
                <>
                  Create Account <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>
        ) : (
          <div className="space-y-6 text-center">
            <div className="p-4 bg-indigo-500/5 rounded-xl border border-indigo-500/10 flex flex-col items-center">
              <ShieldCheck size={40} className="text-indigo-400 mb-2" />
              <h3 className="text-sm font-semibold text-slate-200 mb-1">Instant Guest Access</h3>
              <p className="text-xs text-slate-400 leading-relaxed max-w-xs">
                Log in immediately as an anonymous user. Perfect for testing and quick setups without setting up credentials. You can update your display name anytime!
              </p>
            </div>

            <button
              onClick={handleAnonymousSubmit}
              disabled={loading}
              className="w-full py-3 rounded-lg bg-gradient-to-r from-indigo-500 to-fuchsia-500 text-white font-medium text-sm flex items-center justify-center gap-2 hover:opacity-90 active:scale-[0.98] transition-all disabled:opacity-50 shadow-lg shadow-indigo-500/10 cursor-pointer"
            >
              {loading ? (
                <div className="w-5 h-5 rounded-full border-2 border-white/30 border-t-white animate-spin"></div>
              ) : (
                <>
                  Enter AMDChat Anonymously <ArrowRight size={16} />
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
