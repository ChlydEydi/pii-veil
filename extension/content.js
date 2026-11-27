/* pii-veil for claude.ai
 * 1. When you press Enter / Send, swap sensitive values for fakes, THEN send.
 * 2. Show real values on screen again (Claude's copy stays fake).
 * 3. Badge + panel: on/off, "What Claude saw", "Always hide" list.
 */
(() => {
  "use strict";
  const { Shield } = window.PiiVeil;
  const LOG = (...a) => console.debug("[pii-veil]", ...a);

  let shield = new Shield();
  let names = [];          // "Always hide" list
  let enabled = true;
  let lastSent = "";       // last masked message (what Claude saw)
  let loaded = false;
  let bypass = false;      // true while WE trigger the real send

  // ------------------------------------------------------------ storage
  const store = chrome.storage.local;
  const ready = store.get(["veilState", "veilNames", "veilEnabled", "veilLast"]).then((d) => {
    if (d.veilState) shield = new Shield(d.veilState);
    names = d.veilNames || [];
    enabled = d.veilEnabled !== false;
    lastSent = d.veilLast || "";
    loaded = true;
    render();
    scheduleUnmask(document.body);
  });
  const save = () => store.set({ veilState: shield.toJSON(), veilNames: names, veilEnabled: enabled, veilLast: lastSent });

  // ------------------------------------------------------------ claude.ai DOM
  function composer() {
    return document.querySelector('div.ProseMirror[contenteditable="true"]')
      || document.querySelector('fieldset [contenteditable="true"]')
      || document.querySelector('[contenteditable="true"]');
  }
  function sendButton() {
    return document.querySelector('button[aria-label="Send message"]')
      || document.querySelector('button[aria-label*="Send" i]');
  }
  const composerText = (el) => (el.innerText || "").replace(/ /g, " ").replace(/\n+$/, "");

  // ------------------------------------------------------------ intercept send
  window.addEventListener("keydown", (e) => {
    if (bypass || !enabled || e.key !== "Enter" || e.shiftKey || e.isComposing || e.ctrlKey || e.altKey || e.metaKey) return;
    const c = composer();
    if (!c || !c.contains(e.target)) return;
    if (!composerText(c).trim()) return;
    stop(e);
    protectAndSend(c);
  }, true);

  window.addEventListener("click", (e) => {
    if (bypass || !enabled) return;
    const btn = e.target.closest && e.target.closest("button");
    if (!btn || btn !== sendButton()) return;
    const c = composer();
    if (!c || !composerText(c).trim()) return;
    stop(e);
    protectAndSend(c);
  }, true);

  function stop(e) { e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation(); }

  let busy = false;
  async function protectAndSend(c) {
    if (busy) return;
    busy = true;
    try {
      if (!loaded) await ready;
      const original = composerText(c);
      const { text: masked, entities } = shield.mask(original, names);
      save();
      if (entities.length) {
        await replaceComposer(c, masked);
        const now = composerText(composer() || c);
        const leaked = shield.leaks(now);
        if (leaked.length) {
          toast(`⚠️ Not sent: pii-veil couldn't hide ${leaked.slice(0, 3).join(", ")}. Please try again.`, true);
          LOG("leak check failed", leaked);
          return;
        }
        lastSent = masked;
        save();
        render();
        toast(`🛡 Hid ${entities.length} item${entities.length > 1 ? "s" : ""} before sending to Claude`);
      } else {
        lastSent = original;
        save();
        render();
      }
      await sleep(60);
      realSend();
    } catch (err) {
      LOG(err);
      toast("⚠️ Not sent: pii-veil hit an error. Your message is still in the box.", true);
    } finally {
      busy = false;
    }
  }

  async function replaceComposer(c, text) {
    c.focus();
    selectAll(c);
    // 1st try: a synthetic paste (ProseMirror turns lines into paragraphs properly)
    try {
      const dt = new DataTransfer();
      dt.setData("text/plain", text);
      c.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    } catch (e) { LOG("paste failed", e); }
    await sleep(80);
    if (!shield.leaks(composerText(composer() || c)).length) return;
    // 2nd try: insertText
    const c2 = composer() || c;
    c2.focus();
    selectAll(c2);
    document.execCommand("insertText", false, text);
    await sleep(80);
  }

  function selectAll(el) {
    const range = document.createRange();
    range.selectNodeContents(el);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  function realSend() {
    bypass = true;
    try {
      const btn = sendButton();
      if (btn && !btn.disabled) btn.click();
      else {
        const c = composer();
        c && c.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true, cancelable: true }));
      }
    } finally {
      setTimeout(() => (bypass = false), 300);
    }
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ------------------------------------------------------------ restore real values on screen
  const pending = new Set();
  let scheduled = false;
  function scheduleUnmask(node) {
    if (node) pending.add(node);
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => {
      scheduled = false;
      const nodes = [...pending];
      pending.clear();
      if (!enabled || !shield.mapping().length) return;
      for (const n of nodes) unmaskTree(n);
    }, 30);
  }
  function skip(el) {
    return !el || el.closest("#pii-veil-root, script, style, textarea, input, [contenteditable='true']");
  }
  function unmaskTree(root) {
    if (root.nodeType === Node.TEXT_NODE) return unmaskText(root);
    if (root.nodeType !== Node.ELEMENT_NODE || skip(root)) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const texts = [];
    while (walker.nextNode()) texts.push(walker.currentNode);
    texts.forEach(unmaskText);
  }
  function unmaskText(t) {
    if (!t.nodeValue || t.nodeValue.length < 2 || skip(t.parentElement)) return;
    const real = shield.unmask(t.nodeValue);
    if (real !== t.nodeValue) t.nodeValue = real;
  }
  new MutationObserver((muts) => {
    for (const m of muts) {
      if (m.type === "characterData") scheduleUnmask(m.target);
      else m.addedNodes.forEach((n) => scheduleUnmask(n));
    }
  }).observe(document.documentElement, { childList: true, subtree: true, characterData: true });

  // copying Claude's answer: give the user the real values
  document.addEventListener("copy", (e) => {
    if (!enabled) return;
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || skip(sel.anchorNode && sel.anchorNode.parentElement)) return;
    const txt = sel.toString();
    const real = shield.unmask(txt);
    if (real !== txt) { e.clipboardData.setData("text/plain", real); e.preventDefault(); }
  }, true);

  // ------------------------------------------------------------ files / images warning
  const warnFiles = () => toast("⚠️ pii-veil can't check files or images yet. Anything inside them goes to Claude unmasked.", true);
  window.addEventListener("change", (e) => { if (enabled && e.target.type === "file" && e.target.files && e.target.files.length) warnFiles(); }, true);
  window.addEventListener("drop", (e) => { if (enabled && e.dataTransfer && e.dataTransfer.files.length) warnFiles(); }, true);
  window.addEventListener("paste", (e) => { if (enabled && e.isTrusted && e.clipboardData && e.clipboardData.files.length) warnFiles(); }, true);

  // ------------------------------------------------------------ UI (shadow DOM, so claude.ai styles don't clash)
  const host = document.createElement("div");
  host.id = "pii-veil-root";
  const ui = host.attachShadow({ mode: "open" });
  ui.innerHTML = `
  <style>
    :host { all: initial; }
    * { box-sizing: border-box; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
    .badge { position: fixed; right: 16px; bottom: 16px; z-index: 2147483646; display: flex; align-items: center; gap: 6px;
      padding: 7px 12px; border-radius: 999px; border: 1px solid #c7d2fe; background: #eef2ff; color: #3730a3;
      font-size: 13px; font-weight: 600; cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,.12); }
    .badge.off { background: #f4f4f5; color: #71717a; border-color: #d4d4d8; }
    .panel { position: fixed; right: 16px; bottom: 60px; z-index: 2147483646; width: 380px; max-height: 72vh; overflow: auto;
      background: #fff; color: #18181b; border: 1px solid #e4e4e7; border-radius: 12px; padding: 14px;
      box-shadow: 0 8px 30px rgba(0,0,0,.18); font-size: 13px; display: none; }
    .panel.open { display: block; }
    h3 { margin: 0 0 2px; font-size: 15px; } h4 { margin: 14px 0 6px; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #52525b; }
    .sub { color: #71717a; margin: 0 0 8px; }
    .row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    pre { white-space: pre-wrap; word-break: break-word; background: #fafafa; border: 1px solid #e4e4e7; border-radius: 8px;
      padding: 8px; margin: 0; max-height: 160px; overflow: auto; font: 12px/1.45 ui-monospace, Consolas, monospace; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; } td { padding: 3px 4px; border-bottom: 1px solid #f4f4f5; vertical-align: top; word-break: break-all; }
    td.arrow { color: #a1a1aa; width: 16px; } td.fake { color: #3730a3; }
    textarea { width: 100%; min-height: 60px; border: 1px solid #d4d4d8; border-radius: 8px; padding: 6px; font-size: 12px; resize: vertical; }
    button { border: 1px solid #d4d4d8; background: #fff; border-radius: 8px; padding: 5px 10px; font-size: 12px; cursor: pointer; }
    button.primary { background: #4f46e5; color: #fff; border-color: #4f46e5; }
    button.danger { color: #b91c1c; }
    .switch { position: relative; width: 38px; height: 22px; border-radius: 999px; background: #d4d4d8; cursor: pointer; border: none; padding: 0; }
    .switch::after { content: ""; position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; border-radius: 50%; background: #fff; transition: left .15s; }
    .switch.on { background: #4f46e5; } .switch.on::after { left: 19px; }
    .muted { color: #a1a1aa; font-style: italic; }
    .toast { position: fixed; left: 50%; bottom: 90px; transform: translateX(-50%); z-index: 2147483647; max-width: 520px;
      background: #18181b; color: #fff; padding: 9px 14px; border-radius: 10px; font-size: 13px; opacity: 0; transition: opacity .2s; pointer-events: none; }
    .toast.show { opacity: 1; } .toast.warn { background: #b45309; }
  </style>
  <div class="badge" id="badge"></div>
  <div class="panel" id="panel">
    <div class="row"><h3>🛡 pii-veil</h3><button class="switch" id="toggle" title="Turn protection on/off"></button></div>
    <p class="sub">Claude only receives fake names and details. You see the real ones.</p>
    <h4>What Claude saw (last message)</h4>
    <pre id="last"></pre>
    <h4>Hidden items (real → fake)</h4>
    <div id="map"></div>
    <h4>Always hide these names</h4>
    <p class="sub">One per line. For people the built-in list doesn't know.</p>
    <textarea id="names" placeholder="chlyde iza&#10;Acme Logistics"></textarea>
    <div class="row" style="margin-top:6px"><button class="primary" id="saveNames">Save list</button>
      <button class="danger" id="clear">Forget all hidden items</button></div>
  </div>
  <div class="toast" id="toast"></div>`;
  const $ = (id) => ui.getElementById(id);
  (document.body || document.documentElement).appendChild(host);

  $("badge").onclick = () => { $("panel").classList.toggle("open"); render(); };
  $("toggle").onclick = () => { enabled = !enabled; save(); render(); toast(enabled ? "🛡 pii-veil is ON" : "pii-veil is OFF: messages go to Claude unmasked", !enabled); };
  $("saveNames").onclick = () => {
    names = $("names").value.split("\n").map((s) => s.trim()).filter(Boolean);
    save(); toast(`Saved ${names.length} name${names.length === 1 ? "" : "s"} to always hide`);
  };
  let armed = false;
  $("clear").onclick = () => {
    if (!armed) { armed = true; $("clear").textContent = "Click again to confirm"; setTimeout(() => { armed = false; $("clear").textContent = "Forget all hidden items"; }, 3000); return; }
    armed = false; $("clear").textContent = "Forget all hidden items";
    shield = new Shield(); lastSent = ""; save(); render();
    toast("Forgot all hidden items. Old chats will show fake names now.");
  };

  function render() {
    const rows = shield.mapping();
    $("badge").className = "badge" + (enabled ? "" : " off");
    $("badge").textContent = enabled ? `🛡 pii-veil ON${rows.length ? ` · ${rows.length} hidden` : ""}` : "pii-veil OFF";
    $("toggle").className = "switch" + (enabled ? " on" : "");
    $("last").textContent = lastSent || "Nothing sent yet.";
    $("last").className = lastSent ? "" : "muted";
    $("map").innerHTML = rows.length
      ? "<table>" + rows.map(([r, f]) => `<tr><td>${escHtml(r)}</td><td class="arrow">→</td><td class="fake">${escHtml(f)}</td></tr>`).join("") + "</table>"
      : '<span class="muted">Nothing hidden yet.</span>';
    if (ui.activeElement !== $("names")) $("names").value = names.join("\n");
  }
  const escHtml = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  let toastTimer;
  function toast(msg, warn) {
    const t = $("toast");
    t.textContent = msg;
    t.className = "toast show" + (warn ? " warn" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.className = "toast"), warn ? 6000 : 3000);
  }

  render();
  LOG("loaded");
})();
