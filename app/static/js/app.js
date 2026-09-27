function confirmAction(message) {
  return window.confirm(message || "Are you sure?");
}

function formatBDT(value, withSymbol) {
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return withSymbol === false ? "0.00" : "৳ 0.00";
  }
  const negative = n < 0;
  const abs = Math.abs(n);
  const rounded = Math.round(abs * 100) / 100;
  let [intPart, fracPart] = rounded.toFixed(2).split(".");
  let grouped;
  if (intPart.length <= 3) {
    grouped = intPart;
  } else {
    const last3 = intPart.slice(-3);
    let rest = intPart.slice(0, -3);
    const pairs = [];
    while (rest.length > 0) {
      pairs.unshift(rest.slice(-2));
      rest = rest.slice(0, -2);
    }
    grouped = pairs.join(",") + "," + last3;
  }
  const formatted = (negative ? "-" : "") + grouped + "." + fracPart;
  return withSymbol === false ? formatted : "৳ " + formatted;
}

function parseMoneyInput(raw) {
  if (raw === null || raw === undefined) return 0;
  const cleaned = String(raw).replace(/৳/g, "").replace(/,/g, "").trim();
  if (!cleaned) return 0;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : 0;
}

function recalcBill() {
  const gross = parseMoneyInput(document.getElementById("gross_amount")?.value || 0);
  const vatP = parseMoneyInput(document.getElementById("vat_percent")?.value || 0);
  const tdsP = parseMoneyInput(document.getElementById("tds_percent")?.value || 0);
  const retP = parseMoneyInput(document.getElementById("retention_percent")?.value || 0);
  const vat = Math.round(gross * vatP) / 100;
  const tds = Math.round(gross * tdsP) / 100;
  const ret = Math.round(gross * retP) / 100;
  const net = gross + vat - tds - ret;
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = formatBDT(val); };
  set("preview_vat", vat);
  set("preview_tds", tds);
  set("preview_ret", ret);
  set("preview_net", net);
}

function initSidebarResize() {
  const splitter = document.getElementById("sidebar-splitter");
  if (!splitter) return;
  const KEY = "razz-sidebar-width";
  const MIN = 200;
  const MAX = 520;
  const DEFAULT = 272;
  const apply = (px) => {
    const width = Math.min(MAX, Math.max(MIN, Math.round(px)));
    document.documentElement.style.setProperty("--sidebar", width + "px");
    splitter.setAttribute("aria-valuenow", String(width));
    return width;
  };
  const saved = parseInt(localStorage.getItem(KEY) || "", 10);
  if (saved) apply(saved);
  splitter.setAttribute("aria-valuemin", String(MIN));
  splitter.setAttribute("aria-valuemax", String(MAX));
  let dragging = false;
  splitter.addEventListener("mousedown", (event) => {
    dragging = true;
    document.body.classList.add("is-resizing");
    event.preventDefault();
  });
  window.addEventListener("mousemove", (event) => {
    if (!dragging) return;
    apply(event.clientX);
  });
  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    document.body.classList.remove("is-resizing");
    const current = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--sidebar"), 10);
    localStorage.setItem(KEY, String(current || DEFAULT));
  });
  splitter.addEventListener("dblclick", () => {
    apply(DEFAULT);
    localStorage.setItem(KEY, String(DEFAULT));
  });
  splitter.addEventListener("keydown", (event) => {
    const current = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--sidebar"), 10) || DEFAULT;
    if (event.key === "ArrowLeft") {
      localStorage.setItem(KEY, String(apply(current - 16)));
      event.preventDefault();
    } else if (event.key === "ArrowRight") {
      localStorage.setItem(KEY, String(apply(current + 16)));
      event.preventDefault();
    } else if (event.key === "Home") {
      localStorage.setItem(KEY, String(apply(DEFAULT)));
      event.preventDefault();
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  ["gross_amount", "vat_percent", "tds_percent", "retention_percent"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", recalcBill);
  });
  recalcBill();
  initSidebarResize();
});
