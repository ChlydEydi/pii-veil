/* pii-veil core: detect sensitive values, swap them for realistic fakes, swap back.
 * JavaScript port of veil/detect.py + veil/shield.py (rule detector, no LLM).
 * Works in the browser extension and in Node (for tests).
 */
(function (root) {
  "use strict";

  // ---------------------------------------------------------------- word lists
  const W = (s) => s.trim().split(/\s+/);
  const MALE = new Set(W(`john james robert michael william david richard joseph thomas charles chris
    christopher daniel matthew anthony mark donald steven paul andrew joshua kevin brian george edward
    ronald timothy jason jeffrey ryan jacob gary nicholas eric jonathan stephen larry justin scott
    brandon benjamin samuel frank gregory raymond alexander patrick jack dennis jerry tyler aaron jose
    adam henry nathan peter zachary kyle walter ethan jeremy harold keith christian roger noah gerald
    carl terry sean austin arthur lawrence jesse dylan bryan joe jordan billy bruce albert willie
    gabriel logan alan juan wayne roy ralph randy eugene vincent russell elijah louis bobby philip
    johnny ken kenneth adrian ha hieu minh tuan wei jun ming hao kumar raj arjun ahmad muhammad ali
    omar chen lee kim`));
  const FEMALE = new Set(W(`mary patricia jennifer linda elizabeth barbara susan jessica sarah karen
    lisa nancy betty margaret sandra ashley kimberly emily donna michelle carol amanda dorothy melissa
    deborah stephanie rebecca sharon laura cynthia kathleen amy angela shirley anna brenda pamela emma
    nicole helen samantha katherine christine debra rachel carolyn janet catherine maria heather diane
    ruth julie olivia joyce virginia victoria kelly lauren christina joan evelyn judith megan andrea
    cheryl hannah jacqueline martha gloria teresa ann sara madison frances kathryn janice jean abigail
    alice judy sophia isabella denise amber doris marilyn danielle beverly charlotte natalie theresa
    diana brittany lily mei ling hui yan priya anjali fatimah aisha nur siti jowie`));
  const KNOWN_FIRST = new Set([...MALE, ...FEMALE]);

  const FAKE_MALE = W(`Arlen Bastian Caspar Dorian Emeric Fabian Garrick Hollis Idris Jasper Kellan
    Lucian Magnus Nolan Orson Percival Quentin Rowan Silas Tobias Ulric Valen Wystan Yorick Zane
    Anselm Bram Cormac Desmond Evander Fenwick Gideon Hadrian Jarvis Leander Mortimer Niall Osric
    Phineas Rafferty Soren Thaddeus Upton Vaughn Wolfe Ambrose Barnaby Cillian`);
  const FAKE_FEMALE = W(`Adeline Briony Celeste Delphine Elowen Fenella Giselle Honora Imogen Juniper
    Kestrel Liesel Marisol Noemi Ottilie Perpetua Quilla Rosalind Saoirse Tamsin Ursula Verity
    Wilhelmina Xanthe Yvaine Zinnia Annika Beatrix Clementine Damaris Esme Florentine Genevieve
    Henrietta Isolde Jessamy Leocadia Marguerite Nerys Oriane Philippa Romilly Seraphina Thomasina
    Vivienne Winifred`);
  const FAKE_LAST = W(`Ashworth Blackwood Cresswell Dunmore Ellerby Fairbrook Galloway Hartwell
    Ingleby Jessop Kingsley Lockwood Merriweather Northcott Oakhurst Pemberton Quarrington Ravenscroft
    Sutherland Thistlewood Underhill Vandermeer Whitlock Yardley Abernathy Bellingham Carrington
    Drummond Eastwood Fennimore Grantham Holloway Iverson Kensington Langford Montague Nettleton
    Ormsby Prescott Radcliffe Sterling Templeton Upshaw Wainwright Winterbourne Aldridge Brockhurst`);
  const FAKE_COMPANIES = W(`Brightmoor Calderwood Duskline Emberfield Foxglove Glenhaven Hollowpine
    Ironbark Juniperhill Kestrelwood Larkspur Marlowe Nightingale Oakridge Pinecrest Quillfeather
    Riverstone Silverbirch Thornbury Umberleigh`);
  const FAKE_DOMAINS = FAKE_COMPANIES.map((c) => c.toLowerCase() + ".example");

  const AMBIGUOUS_LOWER = new Set(W(`mark jack frank amber lily carol heather roger christian ha joy
    will may grace rose`));
  const COMMON_WORDS = new Set(W(`a an the and or but so if then than to of in on at by for from with
    about as into onto over under up down out off again also too just still already only even ever
    never not no yes ok okay pls please thanks thank thx hi hey hello bye is am are was were be been
    being do does did done doing have has had having will would shall should can could may might must
    need needs wants want wanted said says say told tells asked asks ask called calls call emailed
    emails email sent sends send replied replies reply wrote writes write went goes go came comes come
    got gets get made makes make took takes take gave gives give saw sees see knows know think thinks
    thought feels feel felt likes like liked here there now today tonight tomorrow yesterday later
    soon morning afternoon evening night week month year monday tuesday wednesday thursday friday
    saturday sunday jan feb mar apr jun jul aug sep sept oct nov dec i me my mine you your yours he him
    his she her hers it its we us our they them their this that these those who whom whose what which
    when where why how all any both each every few many more most other some such own same lol haha
    hahaha lmao omg btw fyi asap eta np ty mr mrs ms dr sir madam team guys everyone green white brown
    black gray grey red blue young long king hill wood bell price cook ward well good bad new old big
    small first last next summarise summarize draft reply write`));
  const NOT_SURNAMES = new Set(W(`The And But For From To In On At Is Was Will Can Has Had Said Says
    Thanks Thank Hi Hello Dear Regards Best Team Monday Tuesday Wednesday Thursday Friday Saturday
    Sunday Please We I He She They Our Your His Her`));
  const ROLE_MAILBOXES = new Set(W(`support info admin sales hello contact help noreply no-reply
    billing hr careers team office`));

  // ---------------------------------------------------------------- patterns
  const EMAIL_RE = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g;
  const URL_RE = /\bhttps?:\/\/[^\s<>"')]+/gi;
  const IPV4_RE = /\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b/g;
  const NRIC_RE = /\b[STFGM]\d{7}[A-Z]\b/g;
  const CARD_RE = /\b(?:\d[ -]?){12,18}\d\b/g;
  const PHONE_RE = /(?<![\w+])(?:\+\d{1,3}[\s-]?)?(?:\(\d{1,4}\)[\s-]?)?\d{3,4}[\s-]?\d{3,4}(?:[\s-]?\d{2,4})?(?!\w)/g;
  const HONORIFIC_RE = /\b(?:Mr|Mrs|Ms|Miss|Mdm|Dr|Prof|Sir|Madam)\.?\s+([A-Z][a-z]+(?:-[A-Z][a-z]+)?(?:\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?)?)/g;
  const WORD_RE = /\b[A-Za-z][A-Za-z'-]*\b/g;
  const PRIORITY = { EMAIL: 0, URL: 1, NRIC: 2, CARD: 3, IP: 4, PHONE: 5, PERSON: 6, CUSTOM: 7 };

  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const onlySpaces = (s) => /^ *$/.test(s);

  function luhnOk(digits) {
    let total = 0, alt = false;
    for (let i = digits.length - 1; i >= 0; i--) {
      let d = +digits[i];
      if (alt) { d *= 2; if (d > 9) d -= 9; }
      total += d; alt = !alt;
    }
    return total % 10 === 0;
  }

  // ---------------------------------------------------------------- detection
  function detect(text, opts) {
    const found = [];
    const push = (start, end, kind) => found.push({ start, end, kind, text: text.slice(start, end) });
    const all = (re, fn) => { re.lastIndex = 0; let m; while ((m = re.exec(text))) fn(m); };

    for (const name of opts.names || []) {
      if (name.trim()) all(new RegExp(`(?<!\\w)${esc(name.trim())}(?!\\w)`, "gi"), (m) => push(m.index, m.index + m[0].length, "PERSON"));
    }
    for (const [known, kind] of Object.entries(opts.known || {})) {
      all(new RegExp(`(?<![\\w@.])${esc(known)}(?![\\w@])`, "gi"), (m) => push(m.index, m.index + m[0].length, kind));
    }
    all(EMAIL_RE, (m) => push(m.index, m.index + m[0].length, "EMAIL"));
    all(URL_RE, (m) => push(m.index, m.index + m[0].replace(/[.,;:!?]+$/, "").length, "URL"));
    all(NRIC_RE, (m) => push(m.index, m.index + m[0].length, "NRIC"));
    all(IPV4_RE, (m) => push(m.index, m.index + m[0].length, "IP"));
    all(CARD_RE, (m) => { const d = m[0].replace(/\D/g, ""); if (d.length >= 13 && d.length <= 19 && luhnOk(d)) push(m.index, m.index + m[0].length, "CARD"); });
    all(PHONE_RE, (m) => { const d = m[0].replace(/\D/g, ""); if (d.length >= 7 && d.length <= 15) push(m.index, m.index + m[0].length, "PHONE"); });
    all(HONORIFIC_RE, (m) => { const s = m.index + m[0].length - m[1].length; push(s, s + m[1].length, "PERSON"); });

    const words = []; all(WORD_RE, (m) => words.push(m));
    words.forEach((m, i) => {
      const w = m[0], low = w.toLowerCase();
      if (!KNOWN_FIRST.has(low)) return;
      const cap = w[0] === w[0].toUpperCase();
      if (!cap && AMBIGUOUS_LOWER.has(low)) return;
      let end = m.index + w.length;
      const nxt = words[i + 1];
      if (nxt && onlySpaces(text.slice(end, nxt.index))) {
        const n = nxt[0], nl = n.toLowerCase();
        const isSurname = cap
          ? n[0] === n[0].toUpperCase() && !NOT_SURNAMES.has(n) && !COMMON_WORDS.has(nl)
          : !COMMON_WORDS.has(nl) && !KNOWN_FIRST.has(nl) && /^[A-Za-z]{2,}$/.test(n);
        if (isSurname) end = nxt.index + n.length;
      }
      push(m.index, end, "PERSON");
    });
    return resolveOverlaps(found);
  }

  function resolveOverlaps(list) {
    const sorted = [...list].sort((a, b) => (b.end - b.start) - (a.end - a.start) || (PRIORITY[a.kind] ?? 9) - (PRIORITY[b.kind] ?? 9) || a.start - b.start);
    const taken = [];
    for (const e of sorted) if (taken.every((t) => e.end <= t.start || e.start >= t.end)) taken.push(e);
    return taken.sort((a, b) => a.start - b.start);
  }

  // ---------------------------------------------------------------- seeded RNG
  function hash32(str) { // xmur3
    let h = 1779033703 ^ str.length;
    for (let i = 0; i < str.length; i++) { h = Math.imul(h ^ str.charCodeAt(i), 3432918353); h = (h << 13) | (h >>> 19); }
    h = Math.imul(h ^ (h >>> 16), 2246822507); h = Math.imul(h ^ (h >>> 13), 3266489909);
    return (h ^= h >>> 16) >>> 0;
  }
  function rng(seed) { // mulberry32
    let a = seed;
    const next = () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    return { next, pick: (arr) => arr[Math.floor(next() * arr.length)], digit: () => String(Math.floor(next() * 10)), int: (lo, hi) => lo + Math.floor(next() * (hi - lo + 1)) };
  }

  // ---------------------------------------------------------------- Shield
  class Shield {
    /** state: {secret, tables:{first,last,domain,value}, originals, known} (JSON-safe) */
    constructor(state) {
      const s = state || {};
      this.secret = s.secret || Math.random().toString(36).slice(2) + Date.now().toString(36);
      this.tables = s.tables || { first: {}, last: {}, domain: {}, value: {} };
      this.originals = s.originals || {};
      this.known = s.known || {};
      this.used = new Set(Object.values(this.tables).flatMap((t) => Object.values(t).map((v) => v.toLowerCase())));
      this.forbid = "";
    }
    toJSON() { return { secret: this.secret, tables: this.tables, originals: this.originals, known: this.known }; }

    /** Mask text. names = user's "Always hide" list. Returns {text, entities}. */
    mask(text, names) {
      const entities = detect(text, { names: names || [], known: this.known });
      for (const e of entities) if (worthRemembering(e)) this.known[e.text.toLowerCase()] = e.kind;
      this.forbid = text.toLowerCase();
      let out = "", pos = 0;
      for (const e of entities) { out += text.slice(pos, e.start) + this.fakeFor(e); pos = e.end; }
      return { text: out + text.slice(pos), entities };
    }

    unmask(text) {
      const pairs = this.reversePairs();
      if (!pairs.length || !text) return text;
      const lookup = new Map(pairs.map(([f, r]) => [f.toLowerCase(), r]));
      const re = new RegExp(`(?<![\\w@.])(${pairs.map(([f]) => esc(f)).join("|")})(?![\\w@])`, "gi");
      return text.replace(re, (got) => {
        const real = lookup.get(got.toLowerCase());
        if (got.length > 1 && got === got.toUpperCase() && got !== got.toLowerCase()) return real.toUpperCase();
        if (got === got.toLowerCase() && real !== real.toLowerCase() && !real.includes("@")) return real.toLowerCase();
        // Claude wrote "Noemi" for a name you typed as "sarah" -> show "Sarah"
        if (/^[A-Z][a-z]/.test(got) && real === real.toLowerCase() && !real.includes("@"))
          return real.replace(/(^|\s)([a-z])/g, (m, sp, c) => sp + c.toUpperCase());
        return real;
      });
    }

    /** [real, fake] rows for the "What Claude saw" panel. */
    mapping() {
      const rows = [];
      for (const t of ["first", "last", "value"]) for (const [k, f] of Object.entries(this.tables[t])) rows.push([this.originals[`${t}:${k}`] || k, f]);
      return rows;
    }

    /** Forget one real value (and anything remembered from it). */
    forget(real) {
      const key = real.toLowerCase();
      for (const t of ["first", "last", "value"]) {
        if (this.tables[t][key] !== undefined) {
          this.used.delete(this.tables[t][key].toLowerCase());
          delete this.tables[t][key];
          delete this.originals[`${t}:${key}`];
        }
      }
      for (const k of Object.keys(this.known)) {
        if (k === key || k.split(/\s+/).includes(key)) delete this.known[k];
      }
    }

    /** Real values that would still leak in `text` (safety check before sending). */
    leaks(text) {
      return this.mapping().map(([r]) => r).filter((r) => r.length > 1 && new RegExp(`(?<![\\w@.])${esc(r)}(?![\\w@])`, "i").test(text));
    }

    reversePairs() {
      const pairs = [];
      for (const [t, m] of Object.entries(this.tables)) for (const [k, f] of Object.entries(m)) pairs.push([f, this.originals[`${t}:${k}`] || k]);
      return pairs.sort((a, b) => b[0].length - a[0].length);
    }

    // --- internals
    r(...parts) { return rng(hash32(this.secret + "|" + parts.join("|"))); }
    remember(table, real) { const k = real.toLowerCase(); if (!this.originals[`${table}:${k}`]) this.originals[`${table}:${k}`] = real; return k; }
    unique(table, key, make) {
      if (this.tables[table][key]) return this.tables[table][key];
      let fake;
      for (let i = 0; i < 200; i++) {
        fake = make(this.r(table, key, i));
        const low = fake.toLowerCase();
        if (!this.used.has(low) && low !== key && !this.forbid.includes(low)) break;
      }
      this.used.add(fake.toLowerCase());
      this.tables[table][key] = fake;
      return fake;
    }
    value(real, make) { return this.unique("value", this.remember("value", real), make); }

    fakeFor(e) {
      const t = e.text;
      switch (e.kind) {
        case "PERSON": return this.fakePerson(t);
        case "EMAIL": return this.fakeEmail(t);
        case "PHONE": return this.value(t, (r) => reshapeDigits(t, r, true));
        case "NRIC": return this.value(t, (r) => t[0] + Array.from({ length: 7 }, r.digit).join("") + String.fromCharCode(65 + r.int(0, 25)));
        case "CARD": return this.value(t, (r) => fakeCard(t, r));
        case "IP": return this.value(t, (r) => `203.0.113.${r.int(1, 254)}`);
        case "URL": return this.value(t, (r) => `https://${this.fakeDomain(host(t))}/p/` + Array.from({ length: 8 }, () => "abcdefghijklmnopqrstuvwxyz0123456789"[r.int(0, 35)]).join(""));
        default: return this.value(t, (r) => r.pick(FAKE_COMPANIES) + (r.next() < 0.3 ? ` ${r.int(2, 99)}` : ""));
      }
    }
    fakePerson(name) {
      const words = name.split(/\s+/), seps = name.match(/\s+/g) || [];
      return words.map((w, i) => {
        const low = w.toLowerCase();
        const first = i === 0 && (words.length > 1 || KNOWN_FIRST.has(low) || low in this.tables.first);
        const fake = first ? this.fakeFirst(w) : this.fakeLast(w);
        return (w === low ? fake.toLowerCase() : fake) + (seps[i] || "");
      }).join("");
    }
    fakeFirst(real) {
      const low = real.toLowerCase();
      const pool = FEMALE.has(low) && !MALE.has(low) ? FAKE_FEMALE : MALE.has(low) && !FEMALE.has(low) ? FAKE_MALE : FAKE_MALE.concat(FAKE_FEMALE);
      return this.unique("first", this.remember("first", real), (r) => r.pick(pool));
    }
    fakeLast(real) { return this.unique("last", this.remember("last", real), (r) => r.pick(FAKE_LAST)); }
    fakeDomain(real) { return this.unique("domain", this.remember("domain", real), (r) => r.pick(FAKE_DOMAINS)); }
    fakeEmail(email) {
      const key = this.remember("value", email);
      if (this.tables.value[key]) return this.tables.value[key];
      const at = email.lastIndexOf("@"), local = email.slice(0, at), domain = email.slice(at + 1);
      const fd = this.fakeDomain(domain);
      return this.unique("value", key, (r) => {
        if (ROLE_MAILBOXES.has(local.toLowerCase())) return `${local}@${fd}`;
        const l = local.split(/([._+-])/).map((p) => {
          if (!p || /^[._+-]$/.test(p)) return p;
          if (/^[A-Za-z]+$/.test(p)) {
            const lp = p.toLowerCase();
            if (lp in this.tables.first || KNOWN_FIRST.has(lp)) return this.fakeFirst(p).toLowerCase();
            if (lp in this.tables.last || p.length > 2) return this.fakeLast(p).toLowerCase();
            return Array.from(p, () => "abcdefghijklmnopqrstuvwxyz"[r.int(0, 25)]).join("");
          }
          return reshapeDigits(p, r, false);
        }).join("");
        return `${l}@${fd}`;
      });
    }
  }

  function worthRemembering(e) {
    const words = e.text.toLowerCase().split(/\s+/);
    if (e.kind !== "PERSON" || words.length > 1) return e.text.length >= 3;
    const w = words[0];
    return w.length >= 3 && !COMMON_WORDS.has(w) && !AMBIGUOUS_LOWER.has(w);
  }
  function reshapeDigits(text, r, keepPrefix) {
    let out = "", i = 0, firstLocal = true;
    if (keepPrefix) { const m = /^\+\d{1,3}/.exec(text); if (m) { out = m[0]; i = m[0].length; } }
    for (const ch of text.slice(i)) {
      if (/\d/.test(ch)) { if (firstLocal && keepPrefix) { out += ch; firstLocal = false; } else out += r.digit(); }
      else out += ch;
    }
    return out;
  }
  function fakeCard(text, r) {
    const n = text.replace(/\D/g, "").length;
    let body = "4000" + Array.from({ length: n - 5 }, r.digit).join("");
    let total = 0;
    [...body].reverse().forEach((ch, i) => { let d = +ch; if (i % 2 === 0) { d *= 2; if (d > 9) d -= 9; } total += d; });
    const digits = (body + ((10 - (total % 10)) % 10))[Symbol.iterator]();
    return text.replace(/\d/g, () => digits.next().value);
  }
  function host(url) { const m = /^https?:\/\/([^/:?#]+)/i.exec(url); return m ? m[1] : url; }

  const api = { Shield, detect, luhnOk };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.PiiVeil = api;
})(typeof self !== "undefined" ? self : this);
