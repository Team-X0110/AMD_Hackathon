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
  isLoading: boolean;
}

const FirebaseConfigContext = createContext<FirebaseConfigContextType | undefined>(undefined);

export const FirebaseConfigProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [config, setConfig] = useState<FirebaseConfig | null>(null);
  const [isConfigured, setIsConfigured] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
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
    }
    
    setIsLoading(false);
  }, []);

  return (
    <FirebaseConfigContext.Provider value={{ config, isConfigured, isLoading }}>
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
