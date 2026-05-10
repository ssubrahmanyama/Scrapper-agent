/* store/authStore.tsx — JWT auth state with secure token storage */

import {
  createContext,
  useContext,
  useEffect,
  useReducer,
  useCallback,
  ReactNode,
} from "react";
import { apiClient } from "../api/client";

// ── Types ─────────────────────────────────────────────────────────────────────
interface User {
  id: string;
  email: string;
  full_name: string;
  subscription_tier: "free" | "basic" | "pro" | "enterprise";
  is_verified: boolean;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

type AuthAction =
  | { type: "SET_LOADING"; payload: boolean }
  | { type: "LOGIN_SUCCESS"; payload: { user: User; accessToken: string } }
  | { type: "LOGOUT" }
  | { type: "REFRESH_TOKEN"; payload: string };

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshAccessToken: () => Promise<boolean>;
}

// ── Security: tokens stored in memory + HttpOnly cookie strategy ──────────────
// Access token: memory only (not localStorage — XSS safe)
// Refresh token: sent as httpOnly cookie by server (CSRF protected via SameSite)
// For SPA fallback: refresh token in sessionStorage only (not localStorage)

const TOKEN_KEY = "ps_rt"; // sessionStorage key — cleared on tab close

function saveRefreshToken(token: string) {
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Private browsing — ignore
  }
}

function loadRefreshToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function clearRefreshToken() {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {}
}

// ── Reducer ───────────────────────────────────────────────────────────────────
const initialState: AuthState = {
  user: null,
  accessToken: null,
  isAuthenticated: false,
  isLoading: true,
};

function authReducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case "SET_LOADING":
      return { ...state, isLoading: action.payload };
    case "LOGIN_SUCCESS":
      return {
        ...state,
        user: action.payload.user,
        accessToken: action.payload.accessToken,
        isAuthenticated: true,
        isLoading: false,
      };
    case "LOGOUT":
      return { ...initialState, isLoading: false };
    case "REFRESH_TOKEN":
      return { ...state, accessToken: action.payload };
    default:
      return state;
  }
}

// ── Context ───────────────────────────────────────────────────────────────────
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(authReducer, initialState);

  const fetchCurrentUser = useCallback(
    async (token: string): Promise<User | null> => {
      try {
        const resp = await apiClient.get<User>("/users/me", {
          headers: { Authorization: `Bearer ${token}` },
        });
        return resp.data;
      } catch {
        return null;
      }
    },
    []
  );

  const refreshAccessToken = useCallback(async (): Promise<boolean> => {
    const rt = loadRefreshToken();
    if (!rt) return false;

    try {
      const resp = await apiClient.post<{
        access_token: string;
        refresh_token: string;
      }>("/auth/refresh", { refresh_token: rt });

      const { access_token, refresh_token: new_rt } = resp.data;
      saveRefreshToken(new_rt);
      dispatch({ type: "REFRESH_TOKEN", payload: access_token });

      // Re-fetch user profile
      const user = await fetchCurrentUser(access_token);
      if (user) {
        dispatch({ type: "LOGIN_SUCCESS", payload: { user, accessToken: access_token } });
      }
      return true;
    } catch {
      clearRefreshToken();
      dispatch({ type: "LOGOUT" });
      return false;
    }
  }, [fetchCurrentUser]);

  // ── Auto-restore session on mount ─────────────────────────────────────────
  useEffect(() => {
    (async () => {
      const rt = loadRefreshToken();
      if (rt) {
        await refreshAccessToken();
      } else {
        dispatch({ type: "SET_LOADING", payload: false });
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Auto-refresh access token 2 min before expiry ─────────────────────────
  useEffect(() => {
    if (!state.isAuthenticated) return;
    const interval = setInterval(refreshAccessToken, 28 * 60 * 1000); // 28 min
    return () => clearInterval(interval);
  }, [state.isAuthenticated, refreshAccessToken]);

  const login = useCallback(
    async (email: string, password: string) => {
      const formData = new URLSearchParams();
      formData.append("username", email);
      formData.append("password", password);

      const resp = await apiClient.post<{
        access_token: string;
        refresh_token: string;
      }>("/auth/login", formData, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });

      const { access_token, refresh_token } = resp.data;
      saveRefreshToken(refresh_token);

      const user = await fetchCurrentUser(access_token);
      if (!user) throw new Error("Failed to fetch user profile");

      dispatch({ type: "LOGIN_SUCCESS", payload: { user, accessToken: access_token } });
    },
    [fetchCurrentUser]
  );

  const logout = useCallback(async () => {
    const rt = loadRefreshToken();
    if (rt) {
      try {
        await apiClient.post("/auth/logout", { refresh_token: rt });
      } catch {}
    }
    clearRefreshToken();
    dispatch({ type: "LOGOUT" });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout, refreshAccessToken }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
