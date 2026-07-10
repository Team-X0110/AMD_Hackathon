import React, { createContext, useContext, useState, useEffect } from 'react';
import { 
  type User, 
  signInAnonymously, 
  signInWithEmailAndPassword, 
  createUserWithEmailAndPassword, 
  signOut, 
  updateProfile, 
  onAuthStateChanged
} from 'firebase/auth';
import { ref, set, get, update } from 'firebase/database';
import { useFirebaseConfig } from './FirebaseConfigContext';
import { initFirebase } from '../firebase';

interface UserProfileData {
  uid: string;
  displayName: string;
  email: string;
  avatarColor: string;
  createdAt: number;
}

interface AuthContextType {
  currentUser: User | null;
  profileData: UserProfileData | null;
  loading: boolean;
  loginAnonymously: () => Promise<void>;
  loginWithEmail: (email: string, password: string) => Promise<void>;
  registerWithEmail: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
  updateUserDisplayName: (name: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const AVATAR_COLORS = [
  'from-pink-500 to-rose-500',
  'from-purple-500 to-indigo-500',
  'from-blue-500 to-cyan-500',
  'from-emerald-500 to-teal-500',
  'from-amber-500 to-orange-500',
  'from-violet-500 to-fuchsia-500',
  'from-teal-500 to-cyan-500',
];

const getRandomAvatarColor = () => {
  return AVATAR_COLORS[Math.floor(Math.random() * AVATAR_COLORS.length)];
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { config, isConfigured } = useFirebaseConfig();
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [profileData, setProfileData] = useState<UserProfileData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [authInstance, setAuthInstance] = useState<any>(null);
  const [dbInstance, setDbInstance] = useState<any>(null);

  // Initialize Firebase when config is valid
  useEffect(() => {
    if (isConfigured && config) {
      try {
        const { auth, db } = initFirebase(config);
        setAuthInstance(auth);
        setDbInstance(db);
      } catch (err) {
        console.error('Firebase initialization error in AuthProvider:', err);
        setLoading(false);
      }
    } else {
      setLoading(false);
    }
  }, [isConfigured, config]);

  // Subscribe to auth state changes and auto sign-in anonymously if no user is authenticated
  useEffect(() => {
    if (!authInstance) return;

    const unsubscribe = onAuthStateChanged(authInstance, async (user) => {
      if (user) {
        setCurrentUser(user);
        // Fetch or create profile data in Realtime Database
        try {
          const userRef = ref(dbInstance, `users/${user.uid}`);
          const snapshot = await get(userRef);
          
          if (snapshot.exists()) {
            setProfileData(snapshot.val() as UserProfileData);
          } else {
            // Create a new profile record
            const newProfile: UserProfileData = {
              uid: user.uid,
              displayName: user.displayName || (user.isAnonymous ? `Guest_${user.uid.substring(0, 5)}` : user.email?.split('@')[0] || 'User'),
              email: user.email || 'Anonymous',
              avatarColor: getRandomAvatarColor(),
              createdAt: Date.now(),
            };
            await set(userRef, newProfile);
            setProfileData(newProfile);
          }
        } catch (err) {
          console.error('Error fetching/setting user profile:', err);
        }
        setLoading(false);
      } else {
        setCurrentUser(null);
        setProfileData(null);
        // Trigger auto anonymous login
        try {
          await signInAnonymously(authInstance);
        } catch (err) {
          console.error('Auto sign-in failed:', err);
          setLoading(false);
        }
      }
    });

    return () => unsubscribe();
  }, [authInstance, dbInstance]);

  const loginAnonymously = async () => {
    if (!authInstance) throw new Error('Firebase Auth not initialized');
    setLoading(true);
    try {
      await signInAnonymously(authInstance);
    } catch (err) {
      setLoading(false);
      throw err;
    }
  };

  const loginWithEmail = async (email: string, password: string) => {
    if (!authInstance) throw new Error('Firebase Auth not initialized');
    setLoading(true);
    try {
      await signInWithEmailAndPassword(authInstance, email, password);
    } catch (err) {
      setLoading(false);
      throw err;
    }
  };

  const registerWithEmail = async (email: string, password: string, displayName: string) => {
    if (!authInstance || !dbInstance) throw new Error('Firebase not initialized');
    setLoading(true);
    try {
      const userCredential = await createUserWithEmailAndPassword(authInstance, email, password);
      const user = userCredential.user;
      
      // Update profile display name in Firebase Auth
      await updateProfile(user, { displayName });
      
      // Create user record in Database
      const newProfile: UserProfileData = {
        uid: user.uid,
        displayName: displayName,
        email: email,
        avatarColor: getRandomAvatarColor(),
        createdAt: Date.now(),
      };
      await set(ref(dbInstance, `users/${user.uid}`), newProfile);
      setProfileData(newProfile);
    } catch (err) {
      setLoading(false);
      throw err;
    }
  };

  const logout = async () => {
    if (!authInstance) throw new Error('Firebase Auth not initialized');
    setLoading(true);
    try {
      await signOut(authInstance);
    } finally {
      setLoading(false);
    }
  };

  const updateUserDisplayName = async (name: string) => {
    if (!authInstance || !currentUser || !dbInstance) throw new Error('Firebase not initialized');
    
    // Update Auth Profile
    await updateProfile(currentUser, { displayName: name });
    
    // Update DB Profile
    const userRef = ref(dbInstance, `users/${currentUser.uid}`);
    await update(userRef, { displayName: name });
    
    // Update Local State
    setProfileData(prev => prev ? { ...prev, displayName: name } : null);
  };

  return (
    <AuthContext.Provider value={{
      currentUser,
      profileData,
      loading,
      loginAnonymously,
      loginWithEmail,
      registerWithEmail,
      logout,
      updateUserDisplayName
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
export type { UserProfileData };
