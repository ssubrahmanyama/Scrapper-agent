/**
 * content.js — PrivacyShield content script
 * Injected on known data broker sites to detect and alert on user's PII.
 *
 * Security notes:
 * - Reads page text only; does NOT modify DOM on third-party sites.
 * - API token stored in chrome.storage.local (not accessible to page JS).
 * - All communication with background via chrome.runtime.sendMessage.
 * - No eval(), no dynamic script injection.
 */

(function () {
  "use strict";

  const BROKER_SITE = window.location.hostname.replace("www.", "");

  /**
   * Extract visible text from the page body (no HTML, no scripts).
   * Limit to 10,000 chars to avoid sending huge payloads.
   */
  function getPageText() {
    const bodyClone = document.body.cloneNode(true);
    // Remove scripts and styles
    bodyClone.querySelectorAll("script, style, noscript, iframe").forEach((el) => el.remove());
    const text = bodyClone.innerText || bodyClone.textContent || "";
    return text.slice(0, 10_000);
  }

  /**
   * Send page content to background worker for PII analysis.
   * Background handles API call so content script never sees the token.
   */
  function analysePageForPII() {
    const pageText = getPageText();
    const pageUrl = window.location.href;

    chrome.runtime.sendMessage(
      {
        type: "ANALYSE_PAGE",
        payload: {
          text: pageText,
          url: pageUrl,
          domain: BROKER_SITE,
        },
      },
      (response) => {
        if (chrome.runtime.lastError) {
          return; // Extension not authenticated, silently skip
        }
        if (response?.hasExposure) {
          showWarningBanner(response.piiCount, pageUrl);
        }
      }
    );
  }

  /**
   * Inject a non-intrusive warning banner at the top of the page.
   * Banner is shadow-DOM isolated to prevent style leakage.
   */
  function showWarningBanner(piiCount, pageUrl) {
    if (document.getElementById("ps-warning-root")) return; // Already shown

    const host = document.createElement("div");
    host.id = "ps-warning-root";
    host.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:2147483647;";

    const shadow = host.attachShadow({ mode: "closed" });

    const banner = document.createElement("div");
    banner.style.cssText = `
      background: #1e293b;
      border-bottom: 2px solid #f59e0b;
      color: #f1f5f9;
      font-family: system-ui, -apple-system, sans-serif;
      font-size: 13px;
      padding: 10px 16px;
      display: flex;
      align-items: center;
      gap: 12px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    `;

    const icon = document.createElement("span");
    icon.textContent = "⚠️";
    icon.style.fontSize = "16px";

    const msg = document.createElement("span");
    msg.textContent = `PrivacyShield detected ${piiCount} potential PII exposure${piiCount !== 1 ? "s" : ""} on ${BROKER_SITE}. `;

    const link = document.createElement("a");
    link.textContent = "View & Remove →";
    link.href = `https://privacyshield.ai/dashboard?alert=${encodeURIComponent(pageUrl)}`;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.style.cssText = "color:#f59e0b;font-weight:600;text-decoration:none;";

    const closeBtn = document.createElement("button");
    closeBtn.textContent = "×";
    closeBtn.style.cssText = `
      margin-left: auto;
      background: none;
      border: none;
      color: #64748b;
      font-size: 18px;
      cursor: pointer;
      padding: 0 4px;
      line-height: 1;
    `;
    closeBtn.addEventListener("click", () => host.remove());

    banner.appendChild(icon);
    banner.appendChild(msg);
    banner.appendChild(link);
    banner.appendChild(closeBtn);
    shadow.appendChild(banner);

    document.documentElement.prepend(host);

    // Auto-dismiss after 30 seconds
    setTimeout(() => host.remove(), 30_000);
  }

  // Run analysis after page is loaded
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", analysePageForPII);
  } else {
    analysePageForPII();
  }
})();
