import { initializeApp, getApps, getApp, type FirebaseApp } from 'firebase/app';
import { getAuth, type Auth } from 'firebase/auth';
import { getDatabase, type Database } from 'firebase/database';
import { type FirebaseConfig } from './context/FirebaseConfigContext';

let app: FirebaseApp | null = null;
let auth: Auth | null = null;
let db: Database | null = null;

export const initFirebase = (config: FirebaseConfig) => {
  if (getApps().length === 0) {
    app = initializeApp(config);
  } else {
    app = getApp();
  }
  auth = getAuth(app);
  db = getDatabase(app);
  return { app, auth, db };
};

export const getFirebase = () => {
  if (!app || !auth || !db) {
    if (getApps().length > 0) {
      app = getApp();
      auth = getAuth(app);
      db = getDatabase(app);
    } else {
      throw new Error('Firebase has not been initialized. Please configure it first.');
    }
  }
  return { app, auth, db };
};
