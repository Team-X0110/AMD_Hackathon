import React, { createContext, useContext, useState, useEffect } from 'react';

export interface FirebaseConfig {
  apiKey: string;
  authDomain: string;
  databaseURL: string;
  projectId: string;
  storageBucket?: string;
  messagingSenderId?: string;
  appId?: string;
}

interface FirebaseConfigContextType {
  config: FirebaseConfig | null;
  isConfigured: boolean;
  saveConfig: (newConfig: FirebaseConfig) => void;
  clearConfig: () => void;
  isLoading: boolean;
}

const FirebaseConfigContext = createContext<FirebaseConfigContextType | undefined>(undefined);

const LOCAL_STORAGE_KEY = 'Chat_firebase_config';

export const FirebaseConfigProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [config, setConfig] = useState<FirebaseConfig | null>(null);
  const [isConfigured, setIsConfigured] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    // 1. Try to read from environment variables
    const envConfig: FirebaseConfig = {
      apiKey: import.meta.env.VITE_FIREBASE_API_KEY || '',
      authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || '',
      databaseURL: import.meta.env.VITE_FIREBASE_DATABASE_URL || '',
      projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || '',
      storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || '',
      messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || '',
      appId: import.meta.env.VITE_FIREBASE_APP_ID || '',
    };

    // Valid if main required parameters exist
    const isEnvValid = 
      envConfig.apiKey && 
      envConfig.authDomain && 
      envConfig.databaseURL && 
      envConfig.projectId;

    if (isEnvValid) {
      setConfig(envConfig);
      setIsConfigured(true);
      setIsLoading(false);
      return;
    }

    // 2. Try to read from localStorage
    try {
      const stored = localStorage.getItem(LOCAL_STORAGE_KEY);
      if (stored) {
        const parsed: FirebaseConfig = JSON.parse(stored);
        if (parsed.apiKey && parsed.authDomain && parsed.databaseURL && parsed.projectId) {
          setConfig(parsed);
          setIsConfigured(true);
        }
      }
    } catch (e) {
      console.error('Error parsing stored Firebase config:', e);
    }
    
    setIsLoading(false);
  }, []);

  const saveConfig = (newConfig: FirebaseConfig) => {
    try {
      localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(newConfig));
      setConfig(newConfig);
      setIsConfigured(true);
    } catch (e) {
      console.error('Error saving Firebase config:', e);
    }
  };

  const clearConfig = () => {
    try {
      localStorage.removeItem(LOCAL_STORAGE_KEY);
      setConfig(null);
      setIsConfigured(false);
      // Reload is required to clear Firebase app instances
      window.location.reload();
    } catch (e) {
      console.error('Error clearing Firebase config:', e);
    }
  };

  return (
    <FirebaseConfigContext.Provider value={{ config, isConfigured, saveConfig, clearConfig, isLoading }}>
      {children}
    </FirebaseConfigContext.Provider>
  );
};

export const useFirebaseConfig = () => {
  const context = useContext(FirebaseConfigContext);
  if (!context) {
    throw new Error('useFirebaseConfig must be used within a FirebaseConfigProvider');
  }
  return context;
};
