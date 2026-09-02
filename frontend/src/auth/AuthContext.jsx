import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { api, clearToken, getToken, setToken } from "../api/client";

/**
 * Global authentication state: who is logged in, and the actions
 * to log in / sign up / log out. Wrap the whole app in <AuthProvider>.
 */
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [seller, setSeller] = useState(null);
  const [loading, setLoading] = useState(true); // initial "am I logged in?" check

  // On first load: if we have a stored token, validate it and load the seller
  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      if (!getToken()) {
        setLoading(false);
        return;
      }
      try {
        const me = await api.auth.me();
        if (!cancelled) setSeller(me);
      } catch {
        // Token expired or invalid — clean it up
        clearToken();
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(
    () => ({
      seller,
      loading,

      async login(email, password) {
        const { access_token: token } = await api.auth.login(email, password);
        setToken(token);
        const me = await api.auth.me();
        setSeller(me);
        return me;
      },

      /** Re-fetch the seller profile (after settings updates). */
      async refresh() {
        const me = await api.auth.me();
        setSeller(me);
        return me;
      },

      async signup(payload) {
        await api.auth.signup(payload); // creates the account
        // Then log in immediately for a smooth experience
        return this.login(payload.email, payload.password);
      },

      logout() {
        clearToken();
        setSeller(null);
      },
    }),
    [seller, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Access auth state from any component. */
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return context;
}
