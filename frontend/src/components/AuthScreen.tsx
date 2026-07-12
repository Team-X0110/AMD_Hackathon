import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Mail, Lock, User as UserIcon, ArrowRight, ShieldCheck } from 'lucide-react';

export const AuthScreen: React.FC = () => {
  const { loginAnonymously, loginWithEmail, registerWithEmail } = useAuth();
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
    <div className="min-h-screen w-full flex bg-dark-bg transition-colors">
      {/* Asymmetric Split Layout */}
      <div className="hidden lg:flex flex-col justify-between w-5/12 bg-dark-surface border-r border-neutral-900 p-12 transition-colors">
        <div>
          <div className="w-12 h-12 bg-brand flex items-center justify-center font-extrabold text-white text-xl mb-8 rounded-md">A</div>
          <h1 className="text-4xl font-extrabold tracking-wider text-white mb-4">AMD Core Gateway</h1>
          <p className="text-neutral-400 text-base leading-relaxed max-w-sm">
            High-performance, localized LLM orchestration engine. Connect to the enterprise cluster and begin secure sessions.
          </p>
        </div>
        <div className="text-sm text-neutral-500 font-mono uppercase tracking-wider leading-relaxed">
          Node: {tab === 'anonymous' ? 'GUEST_0X' : 'AUTH_REQ'} <br />
          Latency: <span className="text-brand font-bold">OPTIMAL</span>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-6 bg-white dark:bg-dark-bg transition-colors">
        <div className="w-full max-w-md">
          
          {/* Mobile Header (hidden on large screens) */}
          <div className="lg:hidden mb-10">
            <div className="w-10 h-10 bg-brand flex items-center justify-center font-extrabold text-white text-lg mb-4 rounded-md">A</div>
            <h1 className="text-3xl font-extrabold text-neutral-900 dark:text-white">AMD Core Gateway</h1>
          </div>

          <div className="mb-8">
            <h2 className="text-2xl font-extrabold text-neutral-900 dark:text-white mb-1.5">
              {tab === 'signin' ? 'Session Sign In' : tab === 'signup' ? 'Request Access' : 'Guest Protocol'}
            </h2>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              {tab === 'anonymous' ? 'Proceed without persistent credentials.' : 'Enter your credentials to continue.'}
            </p>
          </div>

          {/* Tabs switcher */}
          <div className="flex border-b border-neutral-200 dark:border-neutral-800 mb-8">
            <button
              onClick={() => { setTab('signin'); setError(null); }}
              className={`flex-1 py-3.5 text-sm font-bold uppercase tracking-wider transition-all cursor-pointer ${
                tab === 'signin' 
                  ? 'text-neutral-900 dark:text-white border-b-3 border-brand' 
                  : 'text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setTab('signup'); setError(null); }}
              className={`flex-1 py-3.5 text-sm font-bold uppercase tracking-wider transition-all cursor-pointer ${
                tab === 'signup' 
                  ? 'text-neutral-900 dark:text-white border-b-3 border-brand' 
                  : 'text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'
              }`}
            >
              Register
            </button>
            <button
              onClick={() => { setTab('anonymous'); setError(null); }}
              className={`flex-1 py-3.5 text-sm font-bold uppercase tracking-wider transition-all cursor-pointer ${
                tab === 'anonymous' 
                  ? 'text-neutral-900 dark:text-white border-b-3 border-brand' 
                  : 'text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'
              }`}
            >
              Guest
            </button>
          </div>

          {error && (
            <div className="p-4 text-sm bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50 text-red-600 dark:text-red-400 rounded-md mb-8">
              {error}
            </div>
          )}

          {tab !== 'anonymous' ? (
            <form onSubmit={handleSubmit} className="space-y-6">
              {tab === 'signup' && (
                <div>
                  <label className="block text-xs font-bold text-neutral-500 dark:text-neutral-400 mb-2 uppercase tracking-wider">Display Name</label>
                  <div className="relative">
                    <UserIcon className="absolute left-3.5 top-1/2 -translate-y-1/2 text-neutral-400" size={18} />
                    <input
                      type="text"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      placeholder="e.g. Developer X"
                      className="w-full text-base pl-11 pr-4 py-3 rounded-md border border-neutral-300 dark:border-neutral-800 bg-white dark:bg-[#0c0c0c] text-neutral-900 dark:text-neutral-200 focus:outline-none focus:border-brand dark:focus:border-brand transition-colors"
                      required
                    />
                  </div>
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-neutral-500 dark:text-neutral-400 mb-2 uppercase tracking-wider">Email</label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 text-neutral-400" size={18} />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="user@domain.com"
                    className="w-full text-base pl-11 pr-4 py-3 rounded-md border border-neutral-300 dark:border-neutral-800 bg-white dark:bg-[#0c0c0c] text-neutral-900 dark:text-neutral-200 focus:outline-none focus:border-brand dark:focus:border-brand transition-colors"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-neutral-500 dark:text-neutral-400 mb-2 uppercase tracking-wider">Password</label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 text-neutral-400" size={18} />
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full text-base pl-11 pr-4 py-3 rounded-md border border-neutral-300 dark:border-neutral-800 bg-white dark:bg-[#0c0c0c] text-neutral-900 dark:text-neutral-200 focus:outline-none focus:border-brand dark:focus:border-brand transition-colors"
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 rounded-md bg-brand text-white font-bold text-sm flex items-center justify-center gap-2 hover:bg-brand-hover transition-colors disabled:opacity-50 cursor-pointer uppercase tracking-wider shadow-sm"
              >
                {loading ? (
                  <div className="w-5 h-5 rounded-full border-2 border-white/30 border-t-white animate-spin"></div>
                ) : (
                  <>
                    {tab === 'signin' ? 'Authenticate Session' : 'Request Credentials'} <ArrowRight size={18} />
                  </>
                )}
              </button>
            </form>
          ) : (
            <div className="space-y-6">
              <div className="p-6 bg-neutral-50 dark:bg-dark-surface border border-neutral-200 dark:border-neutral-800 rounded-md shadow-sm">
                <ShieldCheck size={28} className="text-brand mb-3.5" />
                <h3 className="text-sm font-bold text-neutral-900 dark:text-white mb-2 uppercase tracking-wider">Guest Access Mode</h3>
                <p className="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">
                  Proceed as an anonymous user. Session data is volatile and will not be linked to a persistent identity. You may configure a display alias post-login.
                </p>
              </div>

              <button
                onClick={handleAnonymousSubmit}
                disabled={loading}
                className="w-full py-3 rounded-md bg-brand text-white font-bold text-sm flex items-center justify-center gap-2 hover:bg-brand-hover transition-colors disabled:opacity-50 cursor-pointer uppercase tracking-wider shadow-sm"
              >
                {loading ? (
                  <div className="w-5 h-5 rounded-full border-2 border-white/30 border-t-white animate-spin"></div>
                ) : (
                  <>
                    Initialize Guest Session <ArrowRight size={18} />
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
