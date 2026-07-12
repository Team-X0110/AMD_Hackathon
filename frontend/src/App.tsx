import React, { useState } from 'react';
import { FirebaseConfigProvider, useFirebaseConfig } from './context/FirebaseConfigContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
// Removed FirebaseSetup import
import { Sidebar } from './components/Sidebar';
import { ChatWindow } from './components/ChatWindow';

const MainLayout: React.FC = () => {
  const { isLoading: isConfigLoading, isConfigured } = useFirebaseConfig();
  const { loading: isAuthLoading, currentUser } = useAuth();
  const [activeChatId, setActiveChatId] = useState<string | null>(null);

  const spinnerScreen = (msg: string) => (
    <div className="min-h-screen w-full flex flex-col items-center justify-center bg-white dark:bg-[#111111]">
      <div className="w-6 h-6 rounded-sm border-2 border-slate-200 dark:border-slate-800 border-t-red-600 dark:border-t-red-600 animate-spin mb-4"></div>
      <p className="text-xs text-slate-500 dark:text-slate-400 font-medium uppercase tracking-wider">{msg}</p>
    </div>
  );

  if (isConfigLoading) return spinnerScreen('Checking configurations...');
  if (!isConfigured) {
    return (
      <div className="min-h-screen w-full flex flex-col items-center justify-center bg-white dark:bg-[#111111]">
        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-2">Missing Configuration</h2>
        <p className="text-sm text-slate-500 max-w-md text-center">
          Provide your Firebase configuration in <code>frontend/.env</code> via <code>VITE_FIREBASE_*</code> variables.
        </p>
      </div>
    );
  }
  if (isAuthLoading) return spinnerScreen('Connecting to AMDChat services...');
  if (!currentUser) return spinnerScreen('Entering chat room...');

  return (
    <div className="h-screen w-screen flex overflow-hidden bg-white dark:bg-[#111111] text-slate-900 dark:text-slate-200 font-sans">
      <Sidebar activeChatId={activeChatId} setActiveChatId={setActiveChatId} />
      <ChatWindow activeChatId={activeChatId} />
    </div>
  );
};

function App() {
  return (
    <ThemeProvider>
      <FirebaseConfigProvider>
        <AuthProvider>
          <MainLayout />
        </AuthProvider>
      </FirebaseConfigProvider>
    </ThemeProvider>
  );
}

export default App;
