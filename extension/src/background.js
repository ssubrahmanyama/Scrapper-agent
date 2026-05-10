/**
 * background.js — PrivacyShield Extension Service Worker
 *
 * Handles:
 *   1. Auth token storage / retrieval (chrome.storage.local)
 *   2. PII analysis API calls (proxied from content scripts)
 *   3. Badge count updates
 *   4. Periodic re-scan alarms
 *
 * Security:
 *   - Token never exposed to content scripts or page context
 *   - All API calls made from background (privileged context)
 *   - host_permissions restricted to api.privacyshield.ai only
 */

"use strict";

const API_BASE = "https://api.privacyshield.ai/api/v1";

// ── Token management ──────────────────────────────────────────────────────────
async function getToken() {
  const result = await chrome.storage.local.get(["ps_access_token"]);
  return result.ps_access_token ?? null;
}

async function setToken(token) {
  await chrome.storage.local.set({ ps_access_token: token });
}

async function clearToken() {
  await chrome.storage.local.remove(["ps_access_token", "ps_refresh_token"]);
}

// ── Message handler ───────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "ANALYSE_PAGE") {
    handleAnalysePage(message.payload, sender).then(sendResponse).catch(() =>
      sendResponse(null)
    );
    return true; // Keep channel open for async response
  }

  if (message.type === "SET_TOKEN") {
    setToken(message.token).then(() => sendResponse({ ok: true }));
    return true;
  }

  if (message.type === "CLEAR_TOKEN") {
    clearToken().then(() => sendResponse({ ok: true }));
    return true;
  }

  if (message.type === "GET_AUTH_STATUS") {
    getToken().then((token) => sendResponse({ authenticated: !!token }));
    return true;
  }
});

/**
 * Analyse a page for PII using the PrivacyShield API.
 * Only called from content scripts on known data broker sites.
 */
async function handleAnalysePage(payload, sender) {
  const token = await getToken();
  if (!token) return { hasExposure: false };

  // Validate sender origin — only our extension's content scripts
  if (!sender.tab) return { hasExposure: false };

  try {
    const resp = await fetch(`${API_BASE}/extension/analyse`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        page_text: payload.text,
        page_url: payload.url,
        domain: payload.domain,
      }),
    });

    if (resp.status === 401) {
      // Token expired — attempt refresh
      const refreshed = await attemptTokenRefresh();
      if (!refreshed) {
        await clearToken();
        return { hasExposure: false };
      }
      return handleAnalysePage(payload, sender); // Retry with new token
    }

    if (!resp.ok) return { hasExposure: false };

    const data = await resp.json();
    const piiCount = data.pii_count ?? 0;

    if (piiCount > 0) {
      // Update extension badge
      chrome.action.setBadgeText({ text: String(piiCount), tabId: sender.tab.id });
      chrome.action.setBadgeBackgroundColor({ color: "#ef4444" });
    }

    return { hasExposure: piiCount > 0, piiCount };
  } catch (err) {
    console.error("[PrivacyShield] Analysis failed:", err);
    return { hasExposure: false };
  }
}

async function attemptTokenRefresh() {
  const result = await chrome.storage.local.get(["ps_refresh_token"]);
  const rt = result.ps_refresh_token;
  if (!rt) return false;

  try {
    const resp = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: rt }),
    });

    if (!resp.ok) return false;

    const data = await resp.json();
    await chrome.storage.local.set({
      ps_access_token: data.access_token,
      ps_refresh_token: data.refresh_token,
    });
    return true;
  } catch {
    return false;
  }
}

// ── Periodic rescan alarm ─────────────────────────────────────────────────────
chrome.alarms.create("periodic-check", { periodInMinutes: 60 });

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== "periodic-check") return;
  const token = await getToken();
  if (!token) return;

  // Notify dashboard of pending check
  chrome.action.setBadgeText({ text: "..." });
  chrome.action.setBadgeBackgroundColor({ color: "#64748b" });

  try {
    const resp = await fetch(`${API_BASE}/scans?limit=1&status=completed`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (resp.ok) {
      chrome.action.setBadgeText({ text: "" });
    }
  } catch {}
});

// ── Install handler ───────────────────────────────────────────────────────────
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") {
    chrome.tabs.create({ url: "https://privacyshield.ai/extension-welcome" });
  }
});
