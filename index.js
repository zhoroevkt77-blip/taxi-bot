const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require("@whiskeysockets/baileys");
const pino = require("pino");
const Database = require("better-sqlite3");

const db = new Database("taxi.db");
db.exec(`
  CREATE TABLE IF NOT EXISTS drivers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, car TEXT,
    from_city TEXT, to_city TEXT,
    time TEXT, price TEXT,
    phone TEXT, seats TEXT,
    comment TEXT,
    created_at REAL
  )
`);

function cleanOldRecords() {
  const cutoff = Date.now() / 1000 - 43200;
  db.prepare("DELETE FROM drivers WHERE created_at < ?").run(cutoff);
}
setInterval(cleanOldRecords, 3600 * 1000);
const regions = {
  "Баткен облусу": ["Баткен","Кадамжай","Лейлек (Раззаков)","Кызыл-Кыя","Сүлүктү"],
  "Жалал-Абад облусу": ["Манас","Сузак","Базар-Коргон","Ноокен","Кара-Көл","Таш-Көмүр","Майлуу-Суу","Ала-Бука","Аксы","Чаткал","Тогуз-Торо"],
  "Нарын облусу": ["Нарын","Ат-Башы","Ак-Талаа","Жумгал","Кочкор"],
  "Ош облусу": ["Ош","Кара-Суу","Араван","Ноокат","Өзгөн","Кара-Кулжа","Алай","Чоң-Алай"],
  "Талас облусу": ["Талас","Бакай-Ата","Кара-Буура","Манас району"],
  "Чүй облусу": ["Жайыл","Токмок","Кемин"],
  "Ысык-Көл облусу": ["Каракол","Балыкчы","Чолпон-Ата","Түп","Ак-Суу","Жети-Өгүз","Тоң"]
};
const regionList = Object.keys(regions);
const users = new Map();
function getUser(jid) {
  if (!users.has(jid)) users.set(jid, { step: "menu", data: {} });
  return users.get(jid);
}
function resetUser(jid) { users.set(jid, { step: "menu", data: {} }); }
const MAIN_MENU = "🚕 *КыргызТакси*\n\nКош келиңиз! Тандаңыз:\n\n1️⃣ — 🚗 Айдоочумун\n2️⃣ — 🔍 Жүргүнчүмүн\n\n*/cancel* — баштапкы менюга кайтуу";
function regionMenu() { let m="🗺 *Облус тандаңыз:*\n\n"; regionList.forEach((r,i)=>{m+=`${i+1}. ${r}\n`;}); return m; }
function cityMenu(r) { const c=regions[r]||[]; let m=`📍 *${r}*\nШаар/район тандаңыз:\n\n`; c.forEach((x,i)=>{m+=`${i+1}. ${x}\n`;}); return m; }
function routeMenu() { return "Маршрут тандаңыз:\n\n1️⃣ — 🏙 Бишкекке барам\n2️⃣ — 🌄 Бишкектен кетем"; }
function searchDrivers(fromCities, toCities) {
  cleanOldRecords();
  let rows;
  if (fromCities) { const ph=fromCities.map(()=>"?").join(","); rows=db.prepare(`SELECT * FROM drivers WHERE from_city IN (${ph}) AND to_city='Бишкек'`).all(...fromCities); }
  else if (toCities) { const ph=toCities.map(()=>"?").join(","); rows=db.prepare(`SELECT * FROM drivers WHERE from_city='Бишкек' AND to_city IN (${ph})`).all(...toCities); }
  return rows||[];
}
function formatDrivers(rows, g) {
  if (!rows.length) return "❌ Азырынча айдоочу табылган жок.";
  const grouped={};
  for (const r of rows) { const k=g==="from"?r.from_city:r.to_city; if(!grouped[k])grouped[k]=[]; grouped[k].push(r); }
  let msg=`✅ Жалпы *${rows.length}* айдоочу табылды:\n\n`;
  for (const [city,drivers] of Object.entries(grouped)) {
    msg+=`📍 *${city}* — ${drivers.length} айдоочу\n`;
    for (const r of drivers) { msg+=`\n🚗 *Айдоочу*\n👤 ${r.name}\n🚘 ${r.car}\n📍 ${r.from_city} → ${r.to_city}\n⏰ ${r.time}\n💰 ${r.price} сом\n🪑 ${r.seats}\n📞 ${r.phone}\n💬 ${r.comment}\n─────────────\n`; }
  }
  return msg;
  async function handleMessage(sock, jid, text) {
  const user = getUser(jid);
  const step = user.step;
  const t = text.trim();
  async function send(msg) { await sock.sendMessage(jid, { text: msg }); }
  if (t === "/cancel" || t.toLowerCase() === "cancel") { resetUser(jid); await send(MAIN_MENU); return; }
  if (step === "menu") {
    if (t === "1") { user.step = "d_name"; await send("Атыңызды жазыңыз:"); }
    else if (t === "2") { user.step = "p_route"; await send(routeMenu()); }
    else { await send(MAIN_MENU); }
    return;
  }
  if (step === "d_name") { user.data.name=t; user.step="d_car"; await send("🚘 Машинаңыздын маркасы:"); return; }
  if (step === "d_car") { user.data.car=t; user.step="d_route"; await send(routeMenu()); return; }
  if (step === "d_route") {
    if (t==="1") { user.data.to="Бишкек"; user.step="d_region_from"; await send(regionMenu()); }
    else if (t==="2") { user.data.from="Бишкек"; user.step="d_region_to"; await send(regionMenu()); }
    else { await send(routeMenu()); }
    return;
  }
  if (step==="d_region_from"||step==="d_region_to") {
    const idx=parseInt(t)-1;
    if (isNaN(idx)||idx<0||idx>=regionList.length) { await send("❗ Туура номер жазыңыз"); return; }
    user.data.selectedRegion=regionList[idx];
    user.step=step==="d_region_from"?"d_city_from":"d_city_to";
    await send(cityMenu(user.data.selectedRegion)); return;
  }
  if (step==="d_city_from"||step==="d_city_to") {
    const cities=regions[user.data.selectedRegion]||[];
    const idx=parseInt(t)-1;
    if (isNaN(idx)||idx<0||idx>=cities.length) { await send("❗ Туура номер жазыңыз"); return; }
    if (step==="d_city_from") user.data.from=cities[idx]; else user.data.to=cities[idx];
    user.step="d_time"; await send("⏰ Качан жолго чыгасыз? (мис: 14:00)"); return;
  }
  if (step==="d_time") { user.data.time=t; user.step="d_price"; await send("💰 Жол кире акы (сом):"); return; }
  if (step==="d_price") { user.data.price=t; user.step="d_seats"; await send("🪑 Бош орун саны:"); return; }
  if (step==="d_seats") { user.data.seats=t; user.step="d_phone"; await send("📱 Телефон номериңиз:"); return; }
  if (step==="d_phone") { user.data.phone=t; user.step="d_comment"; await send("💬 Комментарий (болбосо — сызыкча):"); return; }
  if (step==="d_comment") {
    user.data.comment=t;
    const d=user.data;
    if (!d.name||!d.car||!d.from||!d.to||!d.time||!d.price||!d.seats||!d.phone) { await send("❌ Маалымат жетишсиз."); resetUser(jid); await send(MAIN_MENU); return; }
    cleanOldRecords();
    db.prepare("INSERT INTO drivers (name,car,from_city,to_city,time,price,phone,seats,comment,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)").run(d.name,d.car,d.from,d.to,d.time,d.price,d.phone,d.seats,d.comment||"-",Date.now()/1000);
    await send(`✅ *Жарыяңыз сакталды!*\n\n📍 ${d.from} → ${d.to}\n⏰ ${d.time}\n💰 ${d.price} сом\n📞 ${d.phone}`);
    resetUser(jid); await send(MAIN_MENU); return;
  }
  if (step==="p_route") {
    if (t==="1") { user.data.direction="to"; user.step="p_region"; await send(regionMenu()); }
    else if (t==="2") { user.data.direction="from"; user.step="p_region"; await send(regionMenu()); }
    else { await send(routeMenu()); }
    return;
  }
  if (step==="p_region") {
    const idx=parseInt(t)-1;
    if (isNaN(idx)||idx<0||idx>=regionList.length) { await send("❗ Туура номер жазыңыз"); return; }
    const regionName=regionList[idx];
    const cityList=regions[regionName]||[];
    const direction=user.data.direction;
    let rows,groupField,header;
    if (direction==="to") { rows=searchDrivers(cityList,null); groupField="from"; header=`🔍 *${regionName}* → Бишкекке жөнөгөн айдоочулар:`; }
    else { rows=searchDrivers(null,cityList); groupField="to"; header=`🔍 Бишкектен → *${regionName}* кеткен айдоочулар:`; }
    await send(header); await send(formatDrivers(rows,groupField));
    resetUser(jid); await send(MAIN_MENU); return;
  }
  await send(MAIN_MENU); resetUser(jid);
  }async function startBot() {
  const { state, saveCreds } = await useMultiFileAuthState("auth_info");
  const sock = makeWASocket({
    auth: state,
    printQRInTerminal: true,
    logger: pino({ level: "silent" }),
  });
  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("connection.update", ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      console.log("QR КОД:");
      console.log(qr);
    }
    if (connection === "close") {
      const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
      if (shouldReconnect) startBot();
    } else if (connection === "open") {
      console.log("✅ WhatsApp туташты!");
    }
  });
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const msg of messages) {
      if (msg.key.fromMe) continue;
      if (!msg.message) continue;
      const jid = msg.key.remoteJid;
      const text = msg.message.conversation || msg.message.extendedTextMessage?.text || "";
      if (!text) continue;
      try { await handleMessage(sock, jid, text); } catch (err) { console.error("Ката:", err); }
    }
  });
}

startBot();
}
