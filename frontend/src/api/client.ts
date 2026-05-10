/* api/client.ts — Axios instance with auto token refresh + error normalisation */

import axios, {
  AxiosError,
  AxiosInstance,
  InternalAxiosRequestConfig,
} from "axios";

const BASE_URL =
  (import.meta as any).env?.VITE_API_URL ?? "https://api.privacyshield.ai/api/v1";

// ── In-memory token store (set by auth store after login) ─────────────────────
let _accessToken: string | null = null;
let _refreshPromise: Promise<boolean> | null = null;

export function setAccessToken(token: string | null) {
  _accessToken = token;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

// ── Axios instance ─────────────────────────────────────────────────────────────
export const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
    "X-Client-Version": "1.0.0",
  },
  withCredentials: true,
});

// ── Request interceptor — attach access token ─────────────────────────────────
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    if (_accessToken && config.headers) {
      config.headers.Authorization = `Bearer ${_accessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ── Response interceptor — handle 401 with token refresh ─────────────────────
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url?.includes("/auth/")
    ) {
      originalRequest._retry = true;

      // Coalesce concurrent refresh calls
      if (!_refreshPromise) {
        _refreshPromise = _attemptRefresh().finally(() => {
          _refreshPromise = null;
        });
      }

      const refreshed = await _refreshPromise;
      if (refreshed && _accessToken) {
        originalRequest.headers = originalRequest.headers ?? {};
        originalRequest.headers.Authorization = `Bearer ${_accessToken}`;
        return apiClient(originalRequest);
      }

      // Refresh failed — redirect to login
      window.location.href = "/login?session=expired";
      return Promise.reject(error);
    }

    return Promise.reject(_normaliseError(error));
  }
);

async function _attemptRefresh(): Promise<boolean> {
  const rt = sessionStorage.getItem("ps_rt");
  if (!rt) return false;

  try {
    const resp = await axios.post<{
      access_token: string;
      refresh_token: string;
    }>(`${BASE_URL}/auth/refresh`, { refresh_token: rt });

    _accessToken = resp.data.access_token;
    sessionStorage.setItem("ps_rt", resp.data.refresh_token);
    return true;
  } catch {
    sessionStorage.removeItem("ps_rt");
    return false;
  }
}

export interface APIError {
  code: string;
  message: string;
  detail?: Record<string, unknown>;
  status: number;
}

function _normaliseError(error: AxiosError): APIError {
  const data = error.response?.data as any;
  return {
    code: data?.error?.code ?? "UNKNOWN_ERROR",
    message: data?.error?.message ?? error.message ?? "An unexpected error occurred.",
    detail: data?.error?.detail,
    status: error.response?.status ?? 0,
  };
}

// ── Type-safe API wrappers ─────────────────────────────────────────────────────
export const api = {
  // Auth
  login: (email: string, password: string) => {
    const form = new URLSearchParams({ username: email, password });
    return apiClient.post("/auth/login", form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
  },
  register: (data: { email: string; password: string; full_name: string }) =>
    apiClient.post("/auth/register", data),
  logout: (refreshToken: string) =>
    apiClient.post("/auth/logout", { refresh_token: refreshToken }),

  // Scans
  createScan: (data: {
    target_name: string;
    target_email?: string;
    target_phone?: string;
    target_location?: string;
  }) => apiClient.post("/scans", data),
  listScans: (params?: { skip?: number; limit?: number; status?: string }) =>
    apiClient.get("/scans", { params }),
  getScan: (scanId: string) => apiClient.get(`/scans/${scanId}`),
  deleteScan: (scanId: string) => apiClient.delete(`/scans/${scanId}`),
  rescan: (scanId: string) => apiClient.post(`/scans/${scanId}/rescan`),

  // Removals
  listRemovals: (params?: { skip?: number; limit?: number; status?: string }) =>
    apiClient.get("/removals", { params }),
  processRemoval: (removalId: string) =>
    apiClient.post(`/removals/${removalId}/process`),

  // User
  getMe: () => apiClient.get("/users/me"),
  updateProfile: (data: { full_name?: string; phone?: string }) =>
    apiClient.patch("/users/me", data),

  // Enterprise
  createApiKey: (name: string) => apiClient.post("/enterprise/api-keys", { name }),
  listApiKeys: () => apiClient.get("/enterprise/api-keys"),
  revokeApiKey: (keyId: string) => apiClient.delete(`/enterprise/api-keys/${keyId}`),
};
