import React, { useState } from 'react';
import { FirebaseConfigProvider, useFirebaseConfig } from './context/FirebaseConfigContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { FirebaseSetup } from './components/FirebaseSetup';
import { Sidebar } from './components/Sidebar';
import { ChatWindow } from './components/ChatWindow';

const MainLayout: React.FC = () => {
  const { isLoading: isConfigLoading, isConfigured } = useFirebaseConfig();
  const { loading: isAuthLoading, currentUser } = useAuth();
  const [activeChatId, setActiveChatId] = useState<string | null>(null);

  const spinnerScreen = (msg: string) => (
    <div className="min-h-screen w-full flex flex-col items-center justify-center bg-slate-50 dark:bg-[#090a11]">
      <div className="w-8 h-8 rounded-full border-4 border-indigo-500/20 border-t-indigo-500 animate-spin mb-3"></div>
      <p className="text-xs text-slate-500 dark:text-slate-500 font-medium">{msg}</p>
    </div>
  );

  if (isConfigLoading) return spinnerScreen('Checking configurations...');
  if (!isConfigured) return <FirebaseSetup />;
  if (isAuthLoading) return spinnerScreen('Connecting to AMDChat services...');
  if (!currentUser) return spinnerScreen('Entering chat room...');

  return (
    <div className="h-screen w-screen flex overflow-hidden bg-slate-50 dark:bg-[#090a11] text-slate-900 dark:text-slate-200">
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
