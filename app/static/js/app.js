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

function pad2(n) {
  return String(n).padStart(2, "0");
}

function formatDate(value) {
  if (!value) return "";
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return `${pad2(value.getDate())}/${pad2(value.getMonth() + 1)}/${value.getFullYear()}`;
  }
  const iso = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value).trim());
  if (iso) return `${iso[3]}/${iso[2]}/${iso[1]}`;
  const dmy = /^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/.exec(String(value).trim());
  if (dmy) return `${pad2(dmy[1])}/${pad2(dmy[2])}/${dmy[3]}`;
  return "";
}

function parseDateDmy(str) {
  const m = /^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/.exec(String(str || "").trim());
  if (!m) return null;
  const day = parseInt(m[1], 10);
  const month = parseInt(m[2], 10);
  const year = parseInt(m[3], 10);
  const dt = new Date(year, month - 1, day);
  if (dt.getFullYear() !== year || dt.getMonth() !== month - 1 || dt.getDate() !== day) return null;
  return dt;
}

function toIsoDate(dt) {
  return `${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}-${pad2(dt.getDate())}`;
}

function enhanceDateInputs() {
  document.querySelectorAll('input[type="date"]').forEach((native) => {
    if (native.dataset.enhanced === "1") return;
    native.dataset.enhanced = "1";
    const wrap = document.createElement("span");
    wrap.className = "date-wrap";
    const text = document.createElement("input");
    text.type = "text";
    text.className = "date-input";
    text.name = native.name;
    text.id = native.id;
    text.required = native.required;
    text.placeholder = "DD/MM/YYYY";
    text.maxLength = 10;
    text.autocomplete = "off";
    text.inputMode = "numeric";
    text.spellcheck = false;
    text.title = "Enter date as DD/MM/YYYY";
    text.setAttribute("aria-label", native.getAttribute("aria-label") || native.name || "Date");
    text.value = formatDate(native.value);
    native.removeAttribute("name");
    native.removeAttribute("id");
    native.removeAttribute("required");
    native.classList.add("date-native");
    native.setAttribute("tabindex", "-1");
    native.setAttribute("aria-label", "Choose date from calendar");
    native.title = "Choose date from calendar";
    const cal = document.createElement("span");
    cal.className = "date-cal";
    const icon = document.createElement("span");
    icon.className = "date-cal-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "📅";
    native.addEventListener("change", () => {
      text.value = formatDate(native.value);
      text.setCustomValidity("");
    });
    text.addEventListener("change", () => {
      const parsed = parseDateDmy(text.value);
      if (!parsed) {
        if (text.value.trim()) {
          text.setCustomValidity("Use DD/MM/YYYY, for example 09/03/2026.");
          text.reportValidity();
        }
        return;
      }
      text.setCustomValidity("");
      text.value = formatDate(parsed);
      native.value = toIsoDate(parsed);
    });
    text.addEventListener("input", () => text.setCustomValidity(""));
    native.parentNode.insertBefore(wrap, native);
    wrap.appendChild(text);
    cal.appendChild(native);
    cal.appendChild(icon);
    wrap.appendChild(cal);
  });
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

function initNavLayout() {
  const layout = document.getElementById("app-layout");
  const splitter = document.getElementById("sidebar-splitter");
  const toggle = document.getElementById("nav-toggle");
  if (!layout || !toggle) return;
  const WIDTH_KEY = "razz-sidebar-width";
  const HIDE_KEY = "razz-sidebar-hidden";
  const MIN = 200;
  const MAX = 480;
  const DEFAULT = 272;
  const setWidth = (px) => {
    const width = Math.min(MAX, Math.max(MIN, Math.round(px)));
    layout.style.setProperty("--sidebar", width + "px");
    document.documentElement.style.setProperty("--sidebar", width + "px");
    localStorage.setItem(WIDTH_KEY, String(width));
    return width;
  };
  const setHidden = (hidden) => {
    layout.classList.toggle("nav-hidden", hidden);
    toggle.setAttribute("aria-expanded", hidden ? "false" : "true");
    const label = hidden ? (toggle.dataset.show || "Show navigation") : (toggle.dataset.hide || "Hide navigation");
    toggle.setAttribute("title", label);
    toggle.setAttribute("aria-label", label);
    localStorage.setItem(HIDE_KEY, hidden ? "1" : "0");
  };
  const savedWidth = parseInt(localStorage.getItem(WIDTH_KEY) || "", 10);
  if (Number.isFinite(savedWidth) && savedWidth >= MIN && savedWidth <= MAX) {
    setWidth(savedWidth);
  } else {
    localStorage.removeItem(WIDTH_KEY);
    setWidth(DEFAULT);
  }
  setHidden(localStorage.getItem(HIDE_KEY) === "1");
  toggle.addEventListener("click", () => setHidden(!layout.classList.contains("nav-hidden")));
  if (!splitter) return;
  let dragging = false;
  splitter.addEventListener("mousedown", (event) => {
    if (layout.classList.contains("nav-hidden")) return;
    dragging = true;
    document.body.classList.add("is-resizing");
    event.preventDefault();
  });
  window.addEventListener("mousemove", (event) => {
    if (!dragging) return;
    const left = layout.getBoundingClientRect().left;
    setWidth(event.clientX - left);
  });
  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    document.body.classList.remove("is-resizing");
  });
  splitter.addEventListener("dblclick", () => setWidth(DEFAULT));
}

document.addEventListener("DOMContentLoaded", () => {
  ["gross_amount", "vat_percent", "tds_percent", "retention_percent"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", recalcBill);
  });
  recalcBill();
  initNavLayout();
  enhanceDateInputs();
});
