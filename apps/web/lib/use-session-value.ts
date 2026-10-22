"use client";

// Owner: consultant workspaces. Read browser refresh hints without treating them
// as authority or copying an external store into component state in an effect.
import { useCallback, useSyncExternalStore } from 'react';

const serverSnapshot = () => null;
export function useSessionValue(key: string): string | null {
  const subscribe = useCallback((changed: () => void) => {
    const onStorage = (event: StorageEvent) => { if (event.key === null || event.key === key) changed(); };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [key]);
  const snapshot = useCallback(() => {
    try { return sessionStorage.getItem(key); } catch { return null; }
  }, [key]);
  return useSyncExternalStore(subscribe, snapshot, serverSnapshot);
}
