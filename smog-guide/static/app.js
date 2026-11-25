/**
 * SmogGuide frontend – vanilla JS, no build step, no CDN.
 *
 * Security rules enforced here:
 *  - API data is inserted with textContent / createElement, never innerHTML.
 *  - Form data is validated client-side before submission (server validates too).
 */

"use strict";

const form = document.getElementById("advice-form");
const resultsSection = document.getElementById("results-section");
const resultsContainer = document.getElementById("results-container");

if (!form || !resultsSection || !resultsContainer) {
  throw new Error("Required DOM elements are missing from index.html");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const data = new FormData(/** @type {HTMLFormElement} */ (form));
  const location = (data.get("location") || "").toString().trim();

  if (!location) {
    alert("Please enter your location.");
    return;
  }

  const payload = {
    location,
    household: {
      has_children: data.get("has_children") === "on",
      has_elderly: data.get("has_elderly") === "on",
      has_asthma: data.get("has_asthma") === "on",
      has_heart_condition: data.get("has_heart_condition") === "on",
      has_pregnant: data.get("has_pregnant") === "on",
    },
  };

  clearResults();

  try {
    const response = await fetch("/api/advice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      showError("Could not get advice right now. Please try again.");
      return;
    }

    const result = await response.json();
    renderResults(result);
  } catch {
    showError("Network error. Please check your connection and try again.");
  }
});

/**
 * Render advice results safely using DOM methods (never innerHTML with API data).
 * @param {object} result - Parsed JSON response from /api/advice.
 */
function renderResults(result) {
  if (!result || !Array.isArray(result.recommendations) || result.recommendations.length === 0) {
    const p = document.createElement("p");
    p.textContent = "No recommendations available for your location right now.";
    resultsContainer.appendChild(p);
    resultsSection.hidden = false;
    return;
  }

  const list = document.createElement("ul");
  list.setAttribute("role", "list");

  for (const rec of result.recommendations) {
    const item = document.createElement("li");

    const title = document.createElement("strong");
    title.textContent = rec.title || "";

    const desc = document.createElement("p");
    desc.textContent = rec.description || "";

    item.appendChild(title);
    item.appendChild(desc);
    list.appendChild(item);
  }

  resultsContainer.appendChild(list);
  resultsSection.hidden = false;
}

/** Remove any previously rendered results. */
function clearResults() {
  while (resultsContainer.firstChild) {
    resultsContainer.removeChild(resultsContainer.firstChild);
  }
  resultsSection.hidden = true;
}

/**
 * Display a user-visible error message.
 * @param {string} message - Plain text error message safe to show users.
 */
function showError(message) {
  const p = document.createElement("p");
  p.setAttribute("role", "alert");
  p.textContent = message;
  resultsContainer.appendChild(p);
  resultsSection.hidden = false;
}
