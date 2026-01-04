/* Simple pageview counter + display for static sites (no server required)
 *
 * - Per-post pageviews: element id="pv-post"
 * - Site total pageviews: element id="pv-total"
 *
 * This uses CountAPI (public, no-auth). Counts are "pageviews" (not unique users).
 */

(function () {
  const NAMESPACE = "daewooki-github-io";

  function normalizePath(pathname) {
    if (!pathname) return "/";
    // Remove query/hash parts if any were included accidentally
    const path = pathname.split("?")[0].split("#")[0];
    if (path === "/") return "/";
    return path.endsWith("/") ? path.slice(0, -1) : path;
  }

  function toKey(pathname) {
    const p = normalizePath(pathname);
    if (p === "/") return "home";
    // Keep it URL-safe and short-ish
    return p.replace(/^\//, "").replace(/\//g, "__");
  }

  async function hit(namespace, key) {
    const url = `https://api.countapi.xyz/hit/${encodeURIComponent(namespace)}/${encodeURIComponent(key)}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`countapi: ${res.status}`);
    const data = await res.json();
    return data && typeof data.value === "number" ? data.value : null;
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = value == null ? "-" : String(value);
  }

  (async function main() {
    const path = normalizePath(window.location.pathname || "/");
    const perPostEl = document.getElementById("pv-post");
    const totalEl = document.getElementById("pv-total");

    // Only call endpoints that we need for the current page.
    const jobs = [];

    if (perPostEl) {
      jobs.push(
        hit(NAMESPACE, `pv__${toKey(path)}`).then((v) => setText("pv-post", v)).catch(() => setText("pv-post", "-"))
      );
    }

    if (totalEl) {
      jobs.push(
        hit(NAMESPACE, "pv__total").then((v) => setText("pv-total", v)).catch(() => setText("pv-total", "-"))
      );
    }

    await Promise.all(jobs);
  })();
})();


