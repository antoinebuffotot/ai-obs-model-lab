/* Shared by agent.html : language switcher (same flags and storage key as the chat page) and a minimal markdown renderer. */
const $ = (id) => document.getElementById(id);

const FLAGS = {
  fr: '<rect width="20" height="40" fill="#0055A4"/><rect x="20" width="20" height="40" fill="#fff"/><rect x="40" width="20" height="40" fill="#EF4135"/>',
  en: '<rect width="60" height="40" fill="#012169"/><path d="M0 0L60 40M60 0L0 40" stroke="#fff" stroke-width="8"/><path d="M0 0L60 40M60 0L0 40" stroke="#C8102E" stroke-width="3"/><path d="M30 0V40M0 20H60" stroke="#fff" stroke-width="13"/><path d="M30 0V40M0 20H60" stroke="#C8102E" stroke-width="8"/>',
  es: '<rect width="60" height="40" fill="#AA151B"/><rect y="10" width="60" height="20" fill="#F1BF00"/>',
  de: '<rect width="60" height="13.4" fill="#000"/><rect y="13.3" width="60" height="13.4" fill="#DD0000"/><rect y="26.6" width="60" height="13.4" fill="#FFCE00"/>',
  it: '<rect width="20" height="40" fill="#009246"/><rect x="20" width="20" height="40" fill="#fff"/><rect x="40" width="20" height="40" fill="#CE2B37"/>',
};
const LANGS = [["en", "English"], ["fr", "Français"], ["es", "Español"], ["de", "Deutsch"], ["it", "Italiano"]];
const DECIMAL = { fr: ",", es: ",", de: ",", it: ",", en: "." };

/* dictionary: { fr: {key: text}, en: {...}, ... } ; texts may contain {placeholders} */
function makeI18n(dict) {
  let lang = "fr";
  try { const s = localStorage.getItem("ailab.lang"); if (dict[s]) lang = s; } catch {}
  const api = {
    get lang() { return lang; },
    t(key, vars = {}) {
      return (dict[lang][key] ?? dict.fr[key] ?? key).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
    },
    num(n, digits) { return Number(n).toFixed(digits).replace(".", DECIMAL[lang]); },
    apply() {
      document.documentElement.lang = lang;
      document.title = api.t("pageTitle");
      document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = api.t(el.dataset.i18n); });
      document.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = api.t(el.dataset.i18nPh); });
      document.querySelectorAll("[data-i18n-aria]").forEach((el) => { el.setAttribute("aria-label", api.t(el.dataset.i18nAria)); });
      document.querySelectorAll(".lang button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.lang === lang));
    },
    switcher(boxId, onChange) {
      const box = $(boxId);
      for (const [code, name] of LANGS) {
        const b = document.createElement("button");
        b.type = "button"; b.dataset.lang = code; b.title = name; b.setAttribute("aria-label", name);
        b.innerHTML = '<svg viewBox="0 0 60 40" preserveAspectRatio="none" aria-hidden="true">' + FLAGS[code] + '</svg><span class="ln">' + name + "</span>";
        b.onclick = () => {
          lang = code;
          try { localStorage.setItem("ailab.lang", code); } catch {}
          api.apply(); onChange && onChange();
        };
        box.append(b);
      }
    },
  };
  return api;
}

/* ---------- minimal markdown ---------- */
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function inline(s) {
  return s.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}
function md(src) {
  const blocks = [];
  const text = esc(src).replace(/```[\w-]*\n([\s\S]*?)(```|$)/g, (m, code) => {
    blocks.push("<pre><code>" + code + "</code></pre>");
    return "\u0000" + (blocks.length - 1) + "\u0000";
  });
  const out = []; let list = null, para = [];
  const flushPara = () => { if (para.length) { out.push("<p>" + inline(para.join(" ")) + "</p>"); para = []; } };
  const flushList = () => {
    if (list) { out.push("<" + list.t + ">" + list.items.map((i) => "<li>" + inline(i) + "</li>").join("") + "</" + list.t + ">"); list = null; }
  };
  for (const line of text.split("\n")) {
    let m;
    if ((m = line.match(/^\s*[-*]\s+(.*)/))) { flushPara(); if (!list || list.t !== "ul") { flushList(); list = { t: "ul", items: [] }; } list.items.push(m[1]); }
    else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) { flushPara(); if (!list || list.t !== "ol") { flushList(); list = { t: "ol", items: [] }; } list.items.push(m[1]); }
    else if (/^\u0000\d+\u0000$/.test(line.trim())) { flushPara(); flushList(); out.push(line.trim()); }
    else if (!line.trim()) { flushPara(); flushList(); }
    else if ((m = line.match(/^#{1,4}\s+(.*)/))) { flushPara(); flushList(); out.push("<h4>" + inline(m[1]) + "</h4>"); }
    else { flushList(); para.push(line.trim()); }
  }
  flushPara(); flushList();
  return out.join("").replace(/\u0000(\d+)\u0000/g, (m, i) => blocks[i]);
}
