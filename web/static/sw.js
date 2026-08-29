/* ============================================================
   ТАКСИ роБОТ — service worker
   ============================================================
   Эмне кылат:
   1. Иконкаларды жана манифестти кештейт — тиркеме тез ачылат.
   2. Жарыяларды ЭЧ КАЧАН кештебейт — алар ар дайым жаңы болушу
      керек. Ошондуктан HTML беттери түз серверден алынат.
   3. Интернет жок болсо — кыска эскертүү бети чыгат.

   Версияны өзгөрткөндө эски кеш автоматтык өчөт.
   ============================================================ */

const CACHE = "taxirobot-v1";

// Алдын ала сакталуучу файлдар (жарыялар кирбейт!)
const ASSETS = [
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/icon-maskable-512.png",
  "/manifest.json"
];

// Интернет жок болгондо чыгуучу бет
const OFFLINE_HTML = `<!DOCTYPE html>
<html lang="ky"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Интернет жок</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;
       justify-content:center;background:#f5f5f7;color:#23232a;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
       text-align:center;padding:24px}
  .b{max-width:320px}
  .i{width:64px;height:64px;margin:0 auto 18px;border-radius:20px;
     background:#16161a;display:flex;align-items:center;justify-content:center}
  h1{font-size:21px;font-weight:900;margin:0 0 8px;letter-spacing:-.4px}
  p{font-size:15px;line-height:1.5;color:#8a8a95;margin:0 0 22px}
  button{border:0;background:linear-gradient(135deg,#ffc61a,#ffb703);
         color:#16161a;font:inherit;font-weight:800;font-size:15px;
         padding:14px 28px;border-radius:14px}
</style></head><body>
<div class="b">
  <div class="i">
    <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="#ffc61a"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M3 17v-4l2-5h14l2 5v4"/><path d="M3 17h18"/>
      <circle cx="7.5" cy="17.5" r="1.7"/><circle cx="16.5" cy="17.5" r="1.7"/>
    </svg>
  </div>
  <h1>Интернет жок</h1>
  <p>Жарыяларды көрүү үчүн интернет керек. Байланышты текшерип, кайра аракет кылыңыз.</p>
  <button onclick="location.reload()">Кайра аракет кылуу</button>
</div></body></html>`;

// ---- Орнотуу: керектүү файлдарды сактайбыз ----
self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(ASSETS))
      .catch(() => null)          // бир файл жүктөлбөсө да орнотуу бузулбасын
      .then(() => self.skipWaiting())
  );
});

// ---- Иштетүү: эски версиялардын кешин тазалайбыз ----
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// ---- Сурамдар ----
self.addEventListener("fetch", (e) => {
  const req = e.request;

  // GET эмес сурамдарга кийлигишпейбиз
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Башка домендерди (Telegram, WhatsApp шилтемелери) тийбейбиз
  if (url.origin !== self.location.origin) return;

  // ---- HTML беттери: ар дайым серверден. Жарыялар эскирбеши керек ----
  if (req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html")) {
    e.respondWith(
      fetch(req).catch(() =>
        new Response(OFFLINE_HTML, {
          headers: { "Content-Type": "text/html; charset=utf-8" }
        })
      )
    );
    return;
  }

  // ---- Статикалык файлдар: алгач кештен, жок болсо серверден ----
  e.respondWith(
    caches.match(req).then((hit) => {
      if (hit) return hit;
      return fetch(req).then((res) => {
        if (res && res.status === 200 && res.type === "basic") {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      }).catch(() => hit);
    })
  );
});
