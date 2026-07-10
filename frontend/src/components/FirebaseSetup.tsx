import React, { useState } from 'react';
import { useFirebaseConfig, type FirebaseConfig } from '../context/FirebaseConfigContext';
import { ShieldCheck, FileCode, Sparkles } from 'lucide-react';

export const FirebaseSetup: React.FC = () => {
  const { saveConfig } = useFirebaseConfig();
  const [pasteValue, setPasteValue] = useState('');
  const [formData, setFormData] = useState<FirebaseConfig>({
    apiKey: '',
    authDomain: '',
    databaseURL: '',
    projectId: '',
    storageBucket: '',
    messagingSenderId: '',
    appId: '',
  });
  const [error, setError] = useState<string | null>(null);

  // Auto-parse when pasting a Firebase config snippet
  const handlePasteChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setPasteValue(value);
    setError(null);

    if (!value.trim()) return;

    try {
      // Try parsing as JSON first
      let parsedObj: any = null;
      try {
        parsedObj = JSON.parse(value.trim());
      } catch {
        // If not JSON, try to extract keys using regex (common in JS config snippet)
        const regexMap: { [key in keyof FirebaseConfig]: RegExp } = {
          apiKey: /apiKey:\s*["']([^"']+)["']/i,
          authDomain: /authDomain:\s*["']([^"']+)["']/i,
          databaseURL: /databaseURL:\s*["']([^"']+)["']/i,
          projectId: /projectId:\s*["']([^"']+)["']/i,
          storageBucket: /storageBucket:\s*["']([^"']*)["']/i,
          messagingSenderId: /messagingSenderId:\s*["']([^"']*)["']/i,
          appId: /appId:\s*["']([^"']*)["']/i,
        };

        const extracted: Partial<FirebaseConfig> = {};
        let foundAny = false;
        
        Object.entries(regexMap).forEach(([key, regex]) => {
          const match = value.match(regex);
          if (match && match[1]) {
            extracted[key as keyof FirebaseConfig] = match[1];
            foundAny = true;
          }
        });

        if (foundAny) {
          parsedObj = extracted;
        }
      }

      if (parsedObj) {
        setFormData({
          apiKey: parsedObj.apiKey || '',
          authDomain: parsedObj.authDomain || '',
          databaseURL: parsedObj.databaseURL || '',
          projectId: parsedObj.projectId || '',
          storageBucket: parsedObj.storageBucket || '',
          messagingSenderId: parsedObj.messagingSenderId || '',
          appId: parsedObj.appId || '',
        });
      } else {
        setError('Could not extract config automatically. Please fill in the fields below manually.');
      }
    } catch (err) {
      console.error(err);
      setError('Error parsing configuration block.');
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validate required fields
    const { apiKey, authDomain, databaseURL, projectId } = formData;
    if (!apiKey.trim() || !authDomain.trim() || !databaseURL.trim() || !projectId.trim()) {
      setError('Please fill out all required fields: API Key, Auth Domain, Database URL, and Project ID.');
      return;
    }

    // Save config (triggers provider state update and reload)
    saveConfig({
      apiKey: apiKey.trim(),
      authDomain: authDomain.trim(),
      databaseURL: databaseURL.trim(),
      projectId: projectId.trim(),
      storageBucket: formData.storageBucket?.trim() || '',
      messagingSenderId: formData.messagingSenderId?.trim() || '',
      appId: formData.appId?.trim() || '',
    });
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-slate-50 dark:bg-radial dark:from-slate-900 dark:to-black p-4 md:p-8">
      {/* Background Glows */}
      <div className="absolute top-1/4 left-1/4 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-indigo-500/10 blur-3xl rounded-full pointer-events-none"></div>
      <div className="absolute bottom-1/4 right-1/4 translate-x-1/2 translate-y-1/2 w-96 h-96 bg-fuchsia-500/10 blur-3xl rounded-full pointer-events-none"></div>

      <div className="relative w-full max-w-4xl glass-card rounded-2xl overflow-hidden shadow-2xl z-10 flex flex-col md:flex-row">
        
        {/* Left Side: Information */}
        <div className="w-full md:w-5/12 bg-indigo-50 dark:bg-indigo-950/40 p-6 md:p-8 border-b md:border-b-0 md:border-r border-indigo-100 dark:border-white/5 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-6">
              <span className="w-10 h-10 rounded-xl bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 font-bold text-xl">
                ✨
              </span>
              <span className="text-xl font-bold tracking-tight bg-gradient-to-r from-indigo-700 to-fuchsia-700 dark:from-indigo-200 dark:to-fuchsia-200 bg-clip-text text-transparent">
                AMDChat Setup
              </span>
            </div>
            
            <h2 className="text-2xl font-bold text-white mb-4">Connect Firebase</h2>
            <p className="text-slate-400 text-sm leading-relaxed mb-6">
              To host conversations in real-time, Chat leverages Firebase Authentication and Realtime Database. Follow these simple steps:
            </p>

            <div className="space-y-4">
              <div className="flex gap-3">
                <span className="flex-none w-6 h-6 rounded-full bg-indigo-500/15 border border-indigo-500/30 text-xs font-semibold text-indigo-300 flex items-center justify-center">1</span>
                <div>
                  <h4 className="text-sm font-medium text-slate-200">Create a Firebase Project</h4>
                  <p className="text-xs text-slate-400">Visit Firebase console and initialize a new project.</p>
                </div>
              </div>
              <div className="flex gap-3">
                <span className="flex-none w-6 h-6 rounded-full bg-indigo-500/15 border border-indigo-500/30 text-xs font-semibold text-indigo-300 flex items-center justify-center">2</span>
                <div>
                  <h4 className="text-sm font-medium text-slate-200">Register a Web App</h4>
                  <p className="text-xs text-slate-400">Add a Web application to retrieve your config script block.</p>
                </div>
              </div>
              <div className="flex gap-3">
                <span className="flex-none w-6 h-6 rounded-full bg-indigo-500/15 border border-indigo-500/30 text-xs font-semibold text-indigo-300 flex items-center justify-center">3</span>
                <div>
                  <h4 className="text-sm font-medium text-slate-200">Enable Services</h4>
                  <p className="text-xs text-slate-400">Activate **Anonymous Auth** (or Email/Password) & **Realtime Database**.</p>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-8 pt-6 border-t border-white/5 text-xs text-slate-400">
            <span className="flex items-center gap-1.5 text-indigo-400 font-medium mb-1">
              <ShieldCheck size={14} /> Security Notice
            </span>
            All data is saved locally on your machine in local storage. Nothing is sent to third-party servers.
          </div>
        </div>

        {/* Right Side: Form */}
        <div className="w-full md:w-7/12 p-6 md:p-8 flex flex-col justify-center">
          <form onSubmit={handleSubmit} className="space-y-4">
            
            {/* Quick Auto-Fill */}
            <div>
              <label className="block text-xs font-semibold tracking-wider text-slate-400 uppercase mb-1.5 flex items-center gap-1">
                <FileCode size={12} className="text-indigo-400" /> Paste Firebase Config (Quick Setup)
              </label>
              <textarea
                value={pasteValue}
                onChange={handlePasteChange}
                placeholder={`const firebaseConfig = {\n  apiKey: "AIzaSy...",\n  authDomain: "...",\n  databaseURL: "...",\n  projectId: "..."\n};`}
                rows={4}
                className="w-full text-xs font-mono p-3 rounded-lg border border-white/10 bg-slate-950/40 text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/50 transition-all resize-none"
              />
              <p className="text-[10px] text-slate-500 mt-1">
                Tip: Paste the JavaScript config object directly from console. We will auto-extract it!
              </p>
            </div>

            <div className="relative my-6 flex items-center justify-center">
              <hr className="w-full border-t border-white/5" />
              <span className="absolute px-3 bg-[#121320] text-[10px] uppercase tracking-wider text-slate-500 font-bold">Or enter manually</span>
            </div>

            {error && (
              <div className="p-3 text-xs bg-rose-500/10 border border-rose-500/20 text-rose-300 rounded-lg">
                {error}
              </div>
            )}

            {/* Individual inputs grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">API Key *</label>
                <input
                  type="text"
                  name="apiKey"
                  value={formData.apiKey}
                  onChange={handleInputChange}
                  placeholder="AIzaSy..."
                  className="w-full text-xs p-2.5 rounded-lg border border-white/10 bg-slate-950/40 text-slate-200 focus:outline-none focus:border-indigo-500/50"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Auth Domain *</label>
                <input
                  type="text"
                  name="authDomain"
                  value={formData.authDomain}
                  onChange={handleInputChange}
                  placeholder="your-project.firebaseapp.com"
                  className="w-full text-xs p-2.5 rounded-lg border border-white/10 bg-slate-950/40 text-slate-200 focus:outline-none focus:border-indigo-500/50"
                  required
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-xs font-medium text-slate-400 mb-1">Database URL *</label>
                <input
                  type="text"
                  name="databaseURL"
                  value={formData.databaseURL}
                  onChange={handleInputChange}
                  placeholder="https://your-project-default-rtdb.firebaseio.com"
                  className="w-full text-xs p-2.5 rounded-lg border border-white/10 bg-slate-950/40 text-slate-200 focus:outline-none focus:border-indigo-500/50"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Project ID *</label>
                <input
                  type="text"
                  name="projectId"
                  value={formData.projectId}
                  onChange={handleInputChange}
                  placeholder="your-project-id"
                  className="w-full text-xs p-2.5 rounded-lg border border-white/10 bg-slate-950/40 text-slate-200 focus:outline-none focus:border-indigo-500/50"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Storage Bucket (Optional)</label>
                <input
                  type="text"
                  name="storageBucket"
                  value={formData.storageBucket}
                  onChange={handleInputChange}
                  placeholder="your-project.appspot.com"
                  className="w-full text-xs p-2.5 rounded-lg border border-white/10 bg-slate-950/40 text-slate-200 focus:outline-none focus:border-indigo-500/50"
                />
              </div>
            </div>

            <button
              type="submit"
              className="w-full mt-2 py-3 rounded-lg bg-gradient-to-r from-indigo-500 to-fuchsia-500 text-white font-medium text-sm flex items-center justify-center gap-2 hover:opacity-90 active:scale-[0.98] transition-all shadow-lg shadow-indigo-500/20 cursor-pointer"
            >
              <Sparkles size={16} /> Save Configuration & Launch
            </button>

          </form>
        </div>

      </div>
    </div>
  );
};
