import { initializeApp, getApps, getApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore } from "firebase/firestore";
import { getStorage } from "firebase/storage";

/**
 * Default Firebase web app (project `autoslideshow-54610`).
 * Security is enforced by Firestore/Storage rules + auth, not by hiding the client API key.
 * Override any field with matching `NEXT_PUBLIC_FIREBASE_*` env vars for another environment.
 */
const DEFAULT_FIREBASE_WEB_CONFIG = {
  apiKey: "AIzaSyBCuYFvzugbKGjacBWnsx_Mho-BOrokcOA",
  authDomain: "autoslideshow-54610.firebaseapp.com",
  projectId: "autoslideshow-54610",
  storageBucket: "autoslideshow-54610.firebasestorage.app",
  messagingSenderId: "598758534265",
  appId: "1:598758534265:web:0107dcd0822fa300f4f8a8",
  measurementId: "G-Q4PW5KMHQY",
};

/** Empty env vars on hosts like Vercel must not override embedded defaults (`""` is truthy with `||`). */
function envOr(key, fallback) {
  const v = process.env[key];
  if (v == null || String(v).trim() === "") return fallback;
  return v;
}

function resolvedFirebaseConfig() {
  const d = DEFAULT_FIREBASE_WEB_CONFIG;
  return {
    apiKey: envOr("NEXT_PUBLIC_FIREBASE_API_KEY", d.apiKey),
    authDomain: envOr("NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN", d.authDomain),
    projectId: envOr("NEXT_PUBLIC_FIREBASE_PROJECT_ID", d.projectId),
    storageBucket: envOr("NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET", d.storageBucket),
    messagingSenderId: envOr("NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID", d.messagingSenderId),
    appId: envOr("NEXT_PUBLIC_FIREBASE_APP_ID", d.appId),
    measurementId: envOr("NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID", d.measurementId),
  };
}

/** @returns {boolean} */
export function isFirebaseConfigured() {
  if (typeof window === "undefined") return false;
  const c = resolvedFirebaseConfig();
  return Boolean(c.apiKey && c.projectId && c.storageBucket);
}

/** @returns {import('firebase/app').FirebaseApp | null} */
export function getFirebaseApp() {
  if (!isFirebaseConfigured()) return null;
  if (getApps().length > 0) return getApp();
  return initializeApp(resolvedFirebaseConfig());
}

/** Browser-only: initializes Google Analytics when supported (no-op on SSR / unsupported). */
export async function initFirebaseWebAnalytics() {
  if (typeof window === "undefined") return;
  const app = getFirebaseApp();
  if (!app) return;
  const { measurementId } = resolvedFirebaseConfig();
  if (!measurementId) return;
  const { isSupported, getAnalytics } = await import("firebase/analytics");
  if (await isSupported()) {
    getAnalytics(app);
  }
}

/** @returns {import('firebase/auth').Auth | null} */
export function getFirebaseAuth() {
  const app = getFirebaseApp();
  return app ? getAuth(app) : null;
}

/** @returns {import('firebase/firestore').Firestore | null} */
export function getFirebaseDb() {
  const app = getFirebaseApp();
  return app ? getFirestore(app) : null;
}

/** @returns {import('firebase/storage').FirebaseStorage | null} */
export function getFirebaseStorage() {
  const app = getFirebaseApp();
  return app ? getStorage(app) : null;
}
