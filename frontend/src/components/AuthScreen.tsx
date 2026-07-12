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
    <div className="min-h-screen w-full flex bg-[#0a0a0a]">
      {/* Settings / Reset Firebase Config trigger */}
      <button 
        onClick={clearConfig} 
        title="Reset Firebase Settings"
        className="absolute top-4 right-4 flex items-center gap-1.5 px-3 py-1.5 rounded-sm border border-neutral-800 bg-neutral-900/50 hover:bg-neutral-800 text-neutral-400 hover:text-white transition-all text-xs cursor-pointer z-10"
      >
        <Settings size={14} /> System Config
      </button>

      {/* Asymmetric Split Layout */}
      <div className="hidden lg:flex flex-col justify-between w-5/12 bg-[#111111] border-r border-neutral-900 p-12">
        <div>
          <div className="w-10 h-10 bg-[#ED1C24] flex items-center justify-center font-bold text-white mb-6">A</div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-3">AMDChat</h1>
          <p className="text-neutral-400 text-sm leading-relaxed max-w-sm">
            High-performance, localized LLM orchestration engine. 
            Connect to the enterprise cluster and begin secure sessions.
          </p>
        </div>
        <div className="text-xs text-neutral-600 font-mono uppercase tracking-wider">
          Node: {tab === 'anonymous' ? 'GUEST_0X' : 'AUTH_REQ'} <br />
          Latency: <span className="text-[#ED1C24]">OPTIMAL</span>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-6 bg-white dark:bg-[#0a0a0a]">
        <div className="w-full max-w-sm">
          
          {/* Mobile Header (hidden on large screens) */}
          <div className="lg:hidden mb-10">
            <div className="w-8 h-8 bg-[#ED1C24] flex items-center justify-center font-bold text-white mb-4">A</div>
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">AMDChat</h1>
          </div>

          <div className="mb-6">
            <h2 className="text-xl font-semibold text-neutral-900 dark:text-white mb-1">
              {tab === 'signin' ? 'Session Sign In' : tab === 'signup' ? 'Request Access' : 'Guest Protocol'}
            </h2>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              {tab === 'anonymous' ? 'Proceed without persistent credentials.' : 'Enter your credentials to continue.'}
            </p>
          </div>

          {/* Tabs switcher */}
          <div className="flex border-b border-neutral-200 dark:border-neutral-800 mb-6">
            <button
              onClick={() => { setTab('signin'); setError(null); }}
              className={`flex-1 py-3 text-xs font-semibold uppercase tracking-wider transition-all cursor-pointer ${
                tab === 'signin' 
                  ? 'text-neutral-900 dark:text-white border-b-2 border-[#ED1C24]' 
                  : 'text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setTab('signup'); setError(null); }}
              className={`flex-1 py-3 text-xs font-semibold uppercase tracking-wider transition-all cursor-pointer ${
                tab === 'signup' 
                  ? 'text-neutral-900 dark:text-white border-b-2 border-[#ED1C24]' 
                  : 'text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'
              }`}
            >
              Register
            </button>
            <button
              onClick={() => { setTab('anonymous'); setError(null); }}
              className={`flex-1 py-3 text-xs font-semibold uppercase tracking-wider transition-all cursor-pointer ${
                tab === 'anonymous' 
                  ? 'text-neutral-900 dark:text-white border-b-2 border-[#ED1C24]' 
                  : 'text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'
              }`}
            >
              Guest
            </button>
          </div>

          {error && (
            <div className="p-3 text-xs bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50 text-red-600 dark:text-red-400 rounded-sm mb-6">
              {error}
            </div>
          )}

          {tab !== 'anonymous' ? (
            <form onSubmit={handleSubmit} className="space-y-5">
              {tab === 'signup' && (
                <div>
                  <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-400 mb-1.5 uppercase tracking-wide">Display Name</label>
                  <div className="relative">
                    <UserIcon className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
                    <input
                      type="text"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      placeholder="Identifier"
                      className="w-full text-sm pl-10 pr-4 py-2.5 rounded-sm border border-neutral-300 dark:border-neutral-800 bg-white dark:bg-[#111111] text-neutral-900 dark:text-neutral-200 focus:outline-none focus:border-[#ED1C24] dark:focus:border-[#ED1C24] transition-colors"
                      required
                    />
                  </div>
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-400 mb-1.5 uppercase tracking-wide">Email</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="user@domain.com"
                    className="w-full text-sm pl-10 pr-4 py-2.5 rounded-sm border border-neutral-300 dark:border-neutral-800 bg-white dark:bg-[#111111] text-neutral-900 dark:text-neutral-200 focus:outline-none focus:border-[#ED1C24] dark:focus:border-[#ED1C24] transition-colors"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-400 mb-1.5 uppercase tracking-wide">Password</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full text-sm pl-10 pr-4 py-2.5 rounded-sm border border-neutral-300 dark:border-neutral-800 bg-white dark:bg-[#111111] text-neutral-900 dark:text-neutral-200 focus:outline-none focus:border-[#ED1C24] dark:focus:border-[#ED1C24] transition-colors"
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 rounded-sm bg-[#ED1C24] text-white font-medium text-sm flex items-center justify-center gap-2 hover:bg-[#c9171e] transition-colors disabled:opacity-50 cursor-pointer"
              >
                {loading ? (
                  <div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin"></div>
                ) : (
                  <>
                    {tab === 'signin' ? 'Authenticate' : 'Register'} <ArrowRight size={16} />
                  </>
                )}
              </button>
            </form>
          ) : (
            <div className="space-y-6">
              <div className="p-5 bg-neutral-50 dark:bg-[#111111] border border-neutral-200 dark:border-neutral-800 rounded-sm">
                <ShieldCheck size={24} className="text-[#ED1C24] mb-3" />
                <h3 className="text-sm font-semibold text-neutral-900 dark:text-white mb-2">Guest Access Mode</h3>
                <p className="text-xs text-neutral-600 dark:text-neutral-400 leading-relaxed">
                  Proceed as an anonymous user. Session data is volatile and will not be linked to a persistent identity. You may configure a display alias post-login.
                </p>
              </div>

              <button
                onClick={handleAnonymousSubmit}
                disabled={loading}
                className="w-full py-2.5 rounded-sm bg-[#ED1C24] text-white font-medium text-sm flex items-center justify-center gap-2 hover:bg-[#c9171e] transition-colors disabled:opacity-50 cursor-pointer"
              >
                {loading ? (
                  <div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin"></div>
                ) : (
                  <>
                    Initialize Guest Session <ArrowRight size={16} />
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
