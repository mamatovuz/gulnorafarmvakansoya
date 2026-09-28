const state = {
  token: localStorage.getItem("gf_token") || "",
  me: null,
  profile: null,
  counts: {},
  ref: { branches: [], positions: [], roles: [], users: [] },
  tab: "home",
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const pageRoot = $("#pageRoot");
const modal = $("#modal");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmt(value, fallback = "-") {
  return value === null || value === undefined || value === "" ? fallback : escapeHtml(value);
}

function initials(name) {
  return String(name || "GF")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function toast(message, bad = false) {
  const el = $("#toast");
  el.textContent = message;
  el.style.background = bad ? "#b93d2d" : "#17211d";
  el.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.add("hidden"), 3400);
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  const res = await fetch(path, { ...options, headers });
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    if (!res.ok) throw new Error("Server javob bermadi");
    return res;
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Xatolik yuz berdi");
  return data;
}

async function boot() {
  $("#loginForm").addEventListener("submit", login);
  $("#logoutBtn").addEventListener("click", logout);
  $("#refreshBtn").addEventListener("click", refresh);
  $$(".nav-item").forEach((btn) => btn.addEventListener("click", () => setTab(btn.dataset.tab)));
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {});
  }
  if (!state.token) {
    showLogin();
    return;
  }
  try {
    await loadMe();
    showApp();
    await render();
  } catch (err) {
    localStorage.removeItem("gf_token");
    state.token = "";
    showLogin();
  }
}

async function login(event) {
  event.preventDefault();
  try {
    const identifier = $("#loginIdentifier").value.trim();
    const data = await api("/api/auth/login", { method: "POST", body: { identifier } });
    state.token = data.token;
    localStorage.setItem("gf_token", state.token);
    await loadMe();
    showApp();
    await render();
  } catch (err) {
    toast(err.message, true);
  }
}

function logout() {
  localStorage.removeItem("gf_token");
  state.token = "";
  state.me = null;
  showLogin();
}

function showLogin() {
  $("#loginView").classList.remove("hidden");
  $("#appView").classList.add("hidden");
}

function showApp() {
  $("#loginView").classList.add("hidden");
  $("#appView").classList.remove("hidden");
  $("#roleLabel").textContent = state.me?.role_label || "HR ilova";
  $("#logoutBtn").textContent = initials(state.me?.full_name);
}

async function loadMe() {
  const data = await api("/api/me");
  state.me = data.user;
  state.profile = data.profile;
  state.counts = data.counts || {};
  const ref = await api("/api/reference");
  state.ref = ref;
  updateBadge();
}

async function refresh() {
  try {
    await loadMe();
    await render();
    toast("Yangilandi");
  } catch (err) {
    toast(err.message, true);
  }
}

function updateBadge() {
  const count = Number(state.counts.notifications || 0);
  const badge = $("#navBadge");
  badge.textContent = count > 99 ? "99+" : String(count);
  badge.classList.toggle("hidden", count <= 0);
}

async function setTab(tab) {
  state.tab = tab;
  $$(".nav-item").forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === tab));
  await render();
}

async function render() {
  if (!state.me) return;
  if (state.tab === "home") return renderHome();
  if (state.tab === "attendance") return renderAttendance();
  if (state.tab === "profile") return renderProfile();
  if (state.tab === "notifications") return renderNotifications();
}

function icon(name) {
  const paths = {
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9"/><path d="M16 3.1a4 4 0 0 1 0 7.8"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h5"/>',
    briefcase: '<path d="M10 6V5a2 2 0 0 1 2-2h0a2 2 0 0 1 2 2v1"/><rect x="3" y="6" width="18" height="14" rx="2"/><path d="M3 12h18"/>',
    bell: '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/>',
    map: '<path d="M12 21s7-5.2 7-11a7 7 0 1 0-14 0c0 5.8 7 11 7 11Z"/><circle cx="12" cy="10" r="2.5"/>',
    settings: '<path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"/><path d="M19.4 15a1.8 1.8 0 0 0 .4 2l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.8 1.8 0 0 0-2-.4 1.8 1.8 0 0 0-1 1.6V21a2 2 0 1 1-4 0v-.1a1.8 1.8 0 0 0-1-1.6 1.8 1.8 0 0 0-2 .4l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.8 1.8 0 0 0 .4-2 1.8 1.8 0 0 0-1.6-1H3a2 2 0 1 1 0-4h.1a1.8 1.8 0 0 0 1.6-1 1.8 1.8 0 0 0-.4-2l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.8 1.8 0 0 0 2 .4 1.8 1.8 0 0 0 1-1.6V3a2 2 0 1 1 4 0v.1a1.8 1.8 0 0 0 1 1.6 1.8 1.8 0 0 0 2-.4l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.8 1.8 0 0 0-.4 2 1.8 1.8 0 0 0 1.6 1h.1a2 2 0 1 1 0 4h-.1a1.8 1.8 0 0 0-1.6 1Z"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>',
  };
  return `<svg viewBox="0 0 24 24">${paths[name] || paths.file}</svg>`;
}

async function renderHome() {
  const data = await api("/api/home");
  state.counts = data.counts || state.counts;
  updateBadge();
  const name = state.me.full_name || "Xodim";
  pageRoot.innerHTML = `
    <section class="hero">
      <div class="welcome-panel">
        <div>
          <p class="eyebrow">${fmt(state.me.role_label)}</p>
          <h1 class="hero-title">Salom, <span>${fmt(name.split(" ")[0])}</span></h1>
          <p class="muted">${fmt(state.me.branch_name || "Gulnora Farm")} bo'yicha ishlar bir joyda.</p>
        </div>
        <div class="hero-actions">
          <button class="primary-btn" data-open="application">${icon("plus")} Ariza</button>
          <button class="secondary-btn" data-open="hr_message">${icon("bell")} HR ga murojaat</button>
          <button class="ghost-btn" data-tab-jump="attendance">${icon("map")} Davomat</button>
        </div>
      </div>
      <div class="focus-panel">
        <div>
          <p class="eyebrow">Bugun</p>
          <div class="focus-time" id="homeClock">${new Date().toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" })}</div>
        </div>
        <div class="focus-meta">
          <span>Oy davomidagi kelishlar: <b>${Number(data.counts.attendance_month || 0)}</b></span>
          <span>O'qilmagan xabarlar: <b>${Number(data.counts.notifications || 0)}</b></span>
        </div>
      </div>
    </section>

    <section class="stats-grid">
      ${stat("Faol vakansiya", data.counts.vacancies)}
      ${stat("Mening arizalarim", data.counts.my_applications)}
      ${stat("Xodimlar", data.counts.employees)}
      ${stat("Yangi so'rovlar", Number(data.counts.dayoff_new || 0) + Number(data.counts.staff_regs || 0))}
    </section>

    <section class="section-grid">
      <div class="surface">
        <div class="surface-head"><h2>Ish paneli</h2></div>
        <div class="quick-grid">
          ${quick("Vakansiyalar", "Faol ish o'rinlari", "briefcase", "vacancies")}
          ${quick("Arizalar", "Nomzodlar va holatlar", "file", "applications")}
          ${state.me.permissions.people ? quick("Xodimlar", "Qidiruv va profil", "users", "employees") : ""}
          ${quick("Xodim so'rovlari", "Self-registratsiya", "users", "staff_regs")}
          ${state.me.permissions.hr || state.me.permissions.lead ? quick("Suhbatlar", "Keldi/kelmadi", "file", "interviews") : ""}
          ${quick("So'rovlar", "Dam, maosh, filial", "bell", "requests")}
          ${state.me.permissions.lead ? quick("Davomat hisobot", "Filial kesimi", "map", "attendance_report") : ""}
          ${state.me.permissions.finance ? quick("Moliya", "Oylik va jarima", "briefcase", "finance") : ""}
          ${quick("Avans", "Oylik oldi so'rov", "file", "advance")}
          ${state.me.permissions.lead || state.me.role === "tech" ? quick("Texnik ishlar", "Nosozlik va topshiriq", "settings", "tech") : ""}
          ${state.me.permissions.lead ? quick("Statistika", "Filial va HR kesimi", "file", "stats") : ""}
          ${state.me.permissions.admin ? quick("Admin", "Filial va sozlamalar", "settings", "admin") : ""}
        </div>
      </div>
      <div class="surface">
        <div class="surface-head"><h2>Oxirgi ishlar</h2><button class="ghost-btn" data-workbench="requests">Ko'rish</button></div>
        <div class="list">${renderRequestList(data.requests || [], 5)}</div>
      </div>
    </section>
  `;
  pageRoot.querySelectorAll("[data-tab-jump]").forEach((btn) => btn.addEventListener("click", () => setTab(btn.dataset.tabJump)));
  pageRoot.querySelectorAll("[data-workbench]").forEach((btn) => btn.addEventListener("click", () => openWorkbench(btn.dataset.workbench)));
  pageRoot.querySelectorAll("[data-open]").forEach((btn) => btn.addEventListener("click", () => openCreate(btn.dataset.open)));
}

function stat(label, value) {
  return `<div class="stat-card"><b>${Number(value || 0)}</b><span>${escapeHtml(label)}</span></div>`;
}

function quick(title, text, iconName, workbench) {
  return `
    <button class="quick-card" data-workbench="${workbench}">
      ${icon(iconName)}
      <span><strong>${escapeHtml(title)}</strong><span>${escapeHtml(text)}</span></span>
    </button>
  `;
}

async function renderAttendance() {
  const data = await api("/api/attendance/today");
  const today = data.today || {};
  const checkedIn = Boolean(today.check_in_at);
  const checkedOut = Boolean(today.check_out_at);
  const status = checkedOut ? "Yopilgan" : checkedIn ? "Ishda" : "Kutilmoqda";
  pageRoot.innerHTML = `
    <section class="attendance-layout">
      <div class="surface clock-card">
        <div>
          <p class="eyebrow">Davomat</p>
          <h1>${status}</h1>
          <p class="muted">${fmt(data.profile?.branch_name || state.me.branch_name || "Filial belgilanmagan")}</p>
        </div>
        <div class="clock-ring">
          <div class="clock-inner">
            <strong id="clockNow">${new Date().toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" })}</strong>
            <span>${new Date().toLocaleDateString("uz-UZ")}</span>
          </div>
        </div>
        <div class="attendance-actions">
          <button class="primary-btn" data-att="checkin" ${checkedIn ? "disabled" : ""}>Ishga keldim</button>
          <button class="danger-btn" data-att="checkout" ${!checkedIn || checkedOut ? "disabled" : ""}>Ishdan ketdim</button>
          <button class="secondary-btn" data-att="break_start" ${!checkedIn || checkedOut || today.break_started_at ? "disabled" : ""}>Tanaffus</button>
          <button class="secondary-btn" data-att="break_end" ${!today.break_started_at ? "disabled" : ""}>Davom etish</button>
          <button class="ghost-btn wide" data-workbench="attendance_report">${icon("file")} Hisobot</button>
        </div>
      </div>
      <div class="surface">
        <div class="surface-head"><h2>Bugungi qayd</h2></div>
        <div class="info-grid">
          ${info("Kelish", today.check_in_at)}
          ${info("Ketish", today.check_out_at)}
          ${info("Tanaffus", `${today.break_total_minutes || 0} daqiqa`)}
          ${info("Masofa", today.distance_m ? `${today.distance_m} m` : "-")}
        </div>
        <h3 style="margin-top:18px">Oxirgi kunlar</h3>
        <div class="list">${(data.history || []).map(attendanceItem).join("") || `<div class="empty">Hali davomat yo'q.</div>`}</div>
      </div>
    </section>
  `;
  pageRoot.querySelectorAll("[data-att]").forEach((btn) => btn.addEventListener("click", () => attendanceAction(btn.dataset.att)));
  pageRoot.querySelectorAll("[data-workbench]").forEach((btn) => btn.addEventListener("click", () => openWorkbench(btn.dataset.workbench)));
}

function attendanceItem(item) {
  return `
    <div class="list-item">
      <div class="list-row">
        <span class="list-title">${fmt(item.work_date)}</span>
        <span class="pill ${item.check_out_at ? "" : "warn"}">${item.check_out_at ? "Yopilgan" : "Ochiq"}</span>
      </div>
      <div class="meta">Kelish: ${fmt(item.check_in_at)} · Ketish: ${fmt(item.check_out_at)} · ${fmt(item.note, "")}</div>
    </div>
  `;
}

async function attendanceAction(action) {
  try {
    const needsLocation = action === "checkin" || action === "checkout";
    let payload = {};
    if (needsLocation) {
      toast("GPS olinmoqda...");
      const pos = await getPosition();
      payload = { lat: pos.coords.latitude, lon: pos.coords.longitude };
    }
    const data = await api(`/api/attendance/${action}`, { method: "POST", body: payload });
    toast(data.message || "Qayd qilindi");
    await loadMe();
    await renderAttendance();
  } catch (err) {
    toast(err.message, true);
  }
}

function getPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Brauzer GPS ni qo'llamaydi."));
      return;
    }
    navigator.geolocation.getCurrentPosition(resolve, () => reject(new Error("GPS ruxsati berilmadi.")), {
      enableHighAccuracy: true,
      timeout: 15000,
      maximumAge: 15000,
    });
  });
}

function info(label, value) {
  return `<div class="info-cell"><span>${escapeHtml(label)}</span><b>${fmt(value)}</b></div>`;
}

async function renderProfile() {
  const p = state.profile || {};
  pageRoot.innerHTML = `
    <section class="profile-grid">
      <div class="surface profile-card">
        <div class="profile-avatar">${initials(state.me.full_name)}</div>
        <div>
          <h1>${fmt(state.me.full_name)}</h1>
          <p class="muted">${fmt(state.me.role_label)} · ${fmt(p.branch_name || state.me.branch_name)}</p>
        </div>
        <div class="info-grid">
          ${info("Telefon", state.me.phone)}
          ${info("Lavozim", p.position)}
          ${info("Ish vaqti", p.work_hours)}
          ${info("Dam kuni", p.rest_day)}
          ${info("Oylik", p.monthly_salary)}
          ${info("Ma'lumot", p.education)}
        </div>
      </div>
      <div class="surface">
        <div class="surface-head"><h2>Profilni yangilash</h2></div>
        <form id="profileForm" class="form-grid">
          <label><span>Ism-familiya</span><input name="full_name" value="${fmt(state.me.full_name, "")}" /></label>
          <label><span>Telefon</span><input name="phone" value="${fmt(state.me.phone, "")}" /></label>
          <label class="full"><span>Manzil</span><input name="address" value="${fmt(p.address, "")}" /></label>
          <label><span>Ota/ona telefoni</span><input name="parent_phone" value="${fmt(p.parent_phone, "")}" /></label>
          <label><span>Dam kuni</span><input name="rest_day" value="${fmt(p.rest_day, "")}" /></label>
          <label><span>Ish vaqti</span><input name="work_hours" placeholder="09:00 - 18:00" value="${fmt(p.work_hours, "")}" /></label>
          <label><span>Ma'lumot</span><input name="education" value="${fmt(p.education, "")}" /></label>
          <div class="button-row full">
            <button class="primary-btn" type="submit">Saqlash</button>
            <button class="secondary-btn" type="button" data-open="dayoff">Dam kunini almashtirish</button>
            <button class="secondary-btn" type="button" data-open="work_hours">Ish vaqtini so'rash</button>
            <button class="secondary-btn" type="button" data-open="salary">Maosh so'rash</button>
          </div>
        </form>
      </div>
    </section>
  `;
  $("#profileForm").addEventListener("submit", saveProfile);
  pageRoot.querySelectorAll("[data-open]").forEach((btn) => btn.addEventListener("click", () => openCreate(btn.dataset.open)));
}

async function saveProfile(event) {
  event.preventDefault();
  const body = Object.fromEntries(new FormData(event.currentTarget).entries());
  try {
    const data = await api("/api/profile", { method: "PATCH", body });
    state.me = data.user;
    state.profile = data.profile;
    showApp();
    toast("Profil saqlandi");
    await renderProfile();
  } catch (err) {
    toast(err.message, true);
  }
}

async function renderNotifications() {
  const data = await api("/api/notifications");
  const canSend = state.me.permissions.hr || state.me.permissions.lead;
  pageRoot.innerHTML = `
    <section class="surface">
      <div class="surface-head">
        <h2>Bildirishnomalar</h2>
        ${canSend ? `<button class="primary-btn" data-open="notification">${icon("plus")} Xabar</button>` : ""}
      </div>
      <div class="list">
        ${(data.items || []).map(notificationItem).join("") || `<div class="empty">Bildirishnoma yo'q.</div>`}
      </div>
    </section>
  `;
  pageRoot.querySelectorAll("[data-open]").forEach((btn) => btn.addEventListener("click", () => openCreate(btn.dataset.open)));
  pageRoot.querySelectorAll("[data-read]").forEach((btn) => btn.addEventListener("click", () => markRead(btn.dataset.kind, btn.dataset.read)));
}

function notificationItem(item) {
  const unread = Number(item.read || 0) === 0;
  return `
    <div class="list-item">
      <div class="list-row">
        <span class="list-title">${fmt(item.title || "Xabar")}</span>
        <span class="pill ${unread ? "warn" : "neutral"}">${unread ? "Yangi" : "O'qilgan"}</span>
      </div>
      <div class="meta">${fmt(item.body || item.target_label || "")}</div>
      <div class="list-row">
        <span class="meta">${fmt(item.sender_name || "")} ${fmt(item.created_at || "")}</span>
        ${unread ? `<button class="ghost-btn" data-kind="${fmt(item.kind)}" data-read="${Number(item.id)}">O'qildi</button>` : ""}
      </div>
    </div>
  `;
}

async function markRead(kind, id) {
  try {
    await api("/api/notifications/read", { method: "POST", body: { kind, id: Number(id) } });
    await loadMe();
    await renderNotifications();
  } catch (err) {
    toast(err.message, true);
  }
}

function renderRequestList(items, limit = 100) {
  return items.slice(0, limit).map((item) => `
    <div class="list-item">
      <div class="list-row">
        <span class="list-title">${fmt(requestTitle(item))}</span>
        <span class="pill ${pillClass(item.status)}">${fmt(item.status_label || item.status)}</span>
      </div>
      <div class="meta">${fmt(item.full_name || item.branch_name || "")} · ${fmt(item.created_at)}</div>
      ${(state.me.permissions.lead || state.me.permissions.hr) && ["new", "pending"].includes(String(item.status)) ? `
        <div class="button-row">
          <button class="secondary-btn" data-req-action="approve" data-kind="${fmt(item.kind)}" data-id="${Number(item.id)}">Tasdiqlash</button>
          <button class="danger-btn" data-req-action="reject" data-kind="${fmt(item.kind)}" data-id="${Number(item.id)}">Rad etish</button>
        </div>
      ` : ""}
    </div>
  `).join("") || `<div class="empty">Ma'lumot yo'q.</div>`;
}

function requestTitle(item) {
  if (item.kind === "dayoff") return `Dam kuni: ${item.from_day || "-"} -> ${item.to_day || "-"}`;
  if (item.kind === "work_hours") return `Ish vaqti: ${item.requested_hours || "-"}`;
  if (item.kind === "salary") return `Maosh: ${item.requested_amount || item.offered_amount || "-"}`;
  if (item.kind === "branch_transfer") return `Filial: ${item.from_branch_name || "-"} -> ${item.to_branch_name || "-"}`;
  if (item.kind === "manager_request") return item.title || "Rahbar so'rovi";
  if (item.kind === "hr_message") return item.subject || "HR ga murojaat";
  return item.title || item.kind || "So'rov";
}

function pillClass(status) {
  status = String(status || "");
  if (["rejected", "closed", "declined"].includes(status)) return "bad";
  if (["new", "pending"].includes(status)) return "warn";
  return "";
}

async function openWorkbench(kind) {
  try {
    if (kind === "vacancies") return showVacancies();
    if (kind === "applications") return showApplications();
    if (kind === "employees") return showEmployees();
    if (kind === "requests") return showRequests();
    if (kind === "attendance_report") return showAttendanceReport();
    if (kind === "staff_regs") return showStaffRegs();
    if (kind === "interviews") return showInterviews();
    if (kind === "finance") return showFinance();
    if (kind === "advance") return showAdvance();
    if (kind === "tech") return showTech();
    if (kind === "stats") return showStats();
    if (kind === "admin") return showAdmin();
  } catch (err) {
    toast(err.message, true);
  }
}

async function showVacancies() {
  const data = await api(`/api/vacancies?all=${state.me.permissions.hr ? "1" : "0"}`);
  openModal("Vakansiyalar", `
    <div class="toolbar">
      ${(state.me.permissions.hr || state.me.permissions.manager) ? `<button class="primary-btn" data-open="vacancy">${icon("plus")} Vakansiya</button>` : ""}
    </div>
    <div class="list">${(data.items || []).map((v) => `
      <div class="list-item">
        <div class="list-row"><span class="list-title">${fmt(v.title)}</span><span class="pill">${v.is_active ? "Faol" : "Yopiq"}</span></div>
        <div class="meta">${fmt(v.branch_name)} · ${fmt(v.salary)} · ${fmt(v.work_time || v.shift)}</div>
        <div class="button-row">
          <button class="secondary-btn" data-apply="${Number(v.id)}">Ariza topshirish</button>
          ${(state.me.permissions.hr || state.me.permissions.manager) ? `<button class="ghost-btn" data-close-vac="${Number(v.id)}">${v.is_active ? "Yopish" : "Ochish"}</button>` : ""}
        </div>
      </div>
    `).join("") || `<div class="empty">Vakansiya yo'q.</div>`}</div>
  `);
  modal.querySelectorAll("[data-open]").forEach((btn) => btn.addEventListener("click", () => openCreate(btn.dataset.open)));
  modal.querySelectorAll("[data-apply]").forEach((btn) => btn.addEventListener("click", () => openCreate("application", { vacancy_id: Number(btn.dataset.apply) })));
  modal.querySelectorAll("[data-close-vac]").forEach((btn) => btn.addEventListener("click", () => toggleVacancy(btn.dataset.closeVac)));
}

async function toggleVacancy(id) {
  try {
    const btn = modal.querySelector(`[data-close-vac="${id}"]`);
    const active = btn.textContent.includes("Yopish") ? 0 : 1;
    await api(`/api/vacancies/${id}`, { method: "PATCH", body: { is_active: active, filled: active ? 0 : 1 } });
    toast("Vakansiya yangilandi");
    showVacancies();
  } catch (err) {
    toast(err.message, true);
  }
}

async function showApplications() {
  const data = await api("/api/applications?limit=120");
  openModal("Arizalar", `
    <div class="toolbar">
      <button class="primary-btn" data-open="application">${icon("plus")} Ariza</button>
      ${state.me.permissions.hr ? `<a class="ghost-btn" href="/api/export/applications" target="_blank">${icon("download")} CSV</a>` : ""}
    </div>
    <div class="list">${(data.items || []).map(applicationItem).join("") || `<div class="empty">Ariza yo'q.</div>`}</div>
  `);
  modal.querySelectorAll("[data-open]").forEach((btn) => btn.addEventListener("click", () => openCreate(btn.dataset.open)));
  modal.querySelectorAll("[data-app-action]").forEach((btn) => btn.addEventListener("click", () => applicationAction(btn.dataset.appAction, btn.dataset.id)));
}

function applicationItem(app) {
  return `
    <div class="list-item">
      <div class="list-row">
        <span class="list-title">#${Number(app.id)} · ${fmt(app.full_name)}</span>
        <span class="pill ${pillClass(app.status)}">${fmt(app.status)}</span>
      </div>
      <div class="meta">${fmt(app.position || app.vacancy_title)} · ${fmt(app.branch_name)} · ${fmt(app.phone)}</div>
      ${state.me.permissions.hr ? `
        <div class="button-row">
          <button class="secondary-btn" data-app-action="interview" data-id="${Number(app.id)}">Suhbat</button>
          <button class="secondary-btn" data-app-action="accept" data-id="${Number(app.id)}">Qabul</button>
          <button class="danger-btn" data-app-action="reject" data-id="${Number(app.id)}">Rad</button>
        </div>
      ` : ""}
    </div>
  `;
}

async function applicationAction(action, id) {
  const body = { id: Number(id), action };
  if (action === "reject") body.comment = prompt("Rad etish sababi") || "";
  if (action === "interview") {
    body.date = prompt("Suhbat sanasi (YYYY-MM-DD)") || "";
    body.time = prompt("Vaqti") || "";
    body.location = prompt("Manzil") || "";
  }
  try {
    await api("/api/applications/action", { method: "POST", body });
    toast("Ariza yangilandi");
    showApplications();
  } catch (err) {
    toast(err.message, true);
  }
}

async function showEmployees() {
  const data = await api("/api/employees?limit=200");
  openModal("Xodimlar", `
    <div class="toolbar">
      <input id="empSearch" placeholder="Ism, telefon, lavozim" />
      <button class="secondary-btn" id="empSearchBtn">Qidirish</button>
      <a class="ghost-btn" href="/api/export/employees" target="_blank">${icon("download")} CSV</a>
    </div>
    <div id="empList" class="list">${employeeList(data.items || [])}</div>
  `);
  $("#empSearchBtn", modal).addEventListener("click", async () => {
    const q = $("#empSearch", modal).value.trim();
    const result = await api(`/api/employees?limit=200&q=${encodeURIComponent(q)}`);
    $("#empList", modal).innerHTML = employeeList(result.items || []);
  });
}

function employeeList(items) {
  return items.map((e) => `
    <div class="list-item">
      <div class="list-row"><span class="list-title">${fmt(e.full_name)}</span><span class="pill">${fmt(e.role || e.user_role)}</span></div>
      <div class="meta">${fmt(e.position)} · ${fmt(e.branch_name)} · ${fmt(e.phone)}</div>
      ${state.me.permissions.hr ? `<button class="ghost-btn" data-edit-employee="${Number(e.user_id)}">Tahrirlash</button>` : ""}
    </div>
  `).join("") || `<div class="empty">Xodim topilmadi.</div>`;
}

async function showRequests() {
  const data = await api("/api/requests?limit=120");
  openModal("So'rovlar", `
    <div class="toolbar">
      <button class="primary-btn" data-open="dayoff">${icon("plus")} Dam kuni</button>
      <button class="secondary-btn" data-open="work_hours">Ish vaqti</button>
      <button class="secondary-btn" data-open="salary">Maosh</button>
      <button class="secondary-btn" data-open="branch_transfer">Filial</button>
      <button class="ghost-btn" data-open="hr_message">HR xabar</button>
      ${state.me.permissions.manager || state.me.permissions.hr ? `<button class="ghost-btn" data-open="manager_request">Rahbar so'rovi</button>` : ""}
    </div>
    <div class="list">${renderRequestList(data.items || [])}</div>
  `);
  modal.querySelectorAll("[data-open]").forEach((btn) => btn.addEventListener("click", () => openCreate(btn.dataset.open)));
  modal.querySelectorAll("[data-req-action]").forEach((btn) => btn.addEventListener("click", () => requestAction(btn.dataset.kind, btn.dataset.id, btn.dataset.reqAction)));
}

async function requestAction(kind, id, action) {
  try {
    const body = { kind, id: Number(id), action };
    if (action === "reject") body.reason = prompt("Rad etish sababi") || "";
    await api("/api/requests/action", { method: "POST", body });
    toast("So'rov yangilandi");
    showRequests();
  } catch (err) {
    toast(err.message, true);
  }
}

async function showAttendanceReport() {
  const data = await api("/api/attendance/report");
  openModal("Davomat hisobot", `
    <div class="toolbar">
      <a class="ghost-btn" href="/api/export/attendance" target="_blank">${icon("download")} CSV</a>
    </div>
    <div class="stats-grid">
      ${stat("Kelgan", data.summary.came)}
      ${stat("Ishda", data.summary.open)}
      ${stat("Ketgan", data.summary.closed)}
      ${stat("Kelmagan", data.summary.absent)}
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Xodim</th><th>Filial</th><th>Kelish</th><th>Ketish</th><th>Holat</th></tr></thead>
        <tbody>${(data.items || []).map((r) => `
          <tr><td>${fmt(r.full_name)}</td><td>${fmt(r.branch_name)}</td><td>${fmt(r.check_in_at)}</td><td>${fmt(r.check_out_at)}</td><td>${fmt(r.note)}</td></tr>
        `).join("")}</tbody>
      </table>
    </div>
  `);
}

async function showAdmin() {
  openModal("Admin", `
    <div class="toolbar">
      <button class="primary-btn" data-open="branch">${icon("plus")} Filial</button>
      <button class="secondary-btn" data-open="position">Lavozim</button>
      <button class="ghost-btn" id="settingsBtn">Sozlamalar</button>
    </div>
    <h3>Filiallar</h3>
    <div class="list">${state.ref.branches.map((b) => `
      <div class="list-item">
        <div class="list-row"><span class="list-title">${fmt(b.name)}</span><span class="pill">${fmt(b.radius)} m</span></div>
        <div class="meta">${fmt(b.address)} · ${fmt(b.work_hours)}</div>
      </div>
    `).join("")}</div>
    <h3>Foydalanuvchilar</h3>
    <div class="list">${(state.ref.users || []).slice(0, 80).map((u) => `
      <div class="list-item">
        <div class="list-row"><span class="list-title">${fmt(u.full_name)}</span><span class="pill">${fmt(u.role)}</span></div>
        <div class="meta">${fmt(u.tg_id)} · ${fmt(u.phone)} · filial #${fmt(u.branch_id)}</div>
        <div class="button-row">
          <button class="ghost-btn" data-user-role="${Number(u.id)}">Rol</button>
          <button class="danger-btn" data-user-block="${Number(u.id)}">${u.blocked ? "Blokdan chiqarish" : "Bloklash"}</button>
        </div>
      </div>
    `).join("") || `<div class="empty">Foydalanuvchi yo'q.</div>`}</div>
  `);
  modal.querySelectorAll("[data-open]").forEach((btn) => btn.addEventListener("click", () => openCreate(btn.dataset.open)));
  $("#settingsBtn", modal)?.addEventListener("click", showSettings);
  modal.querySelectorAll("[data-user-role]").forEach((btn) => btn.addEventListener("click", () => updateUserRole(btn.dataset.userRole)));
  modal.querySelectorAll("[data-user-block]").forEach((btn) => btn.addEventListener("click", () => toggleUserBlock(btn.dataset.userBlock, btn.textContent.includes("Blokdan"))));
}

async function showStats() {
  const data = await api("/api/stats");
  openModal("Statistika", `
    <div class="stats-grid">
      ${stat("Foydalanuvchi", data.totals.users)}
      ${stat("Xodim", data.totals.employees)}
      ${stat("Ariza", data.totals.applications)}
      ${stat("Texnik ochiq", data.totals.tech_open)}
    </div>
    <section class="section-grid">
      <div class="surface">
        <h3>Filiallar</h3>
        <div class="list">${(data.branches || []).map((b) => `
          <div class="list-item">
            <div class="list-row"><span class="list-title">${fmt(b.name)}</span><span class="pill">${Number(b.employees || 0)} xodim</span></div>
            <div class="meta">Forma muammo: ${Number(b.uniform_issues || 0)}</div>
          </div>
        `).join("")}</div>
      </div>
      <div class="surface">
        <h3>Rollar va arizalar</h3>
        <div class="list">
          ${(data.roles || []).map((r) => `<div class="list-item"><div class="list-row"><b>${fmt(r.role)}</b><span class="pill">${Number(r.count || 0)}</span></div></div>`).join("")}
          ${(data.applications || []).map((r) => `<div class="list-item"><div class="list-row"><b>Ariza: ${fmt(r.status)}</b><span class="pill ${pillClass(r.status)}">${Number(r.count || 0)}</span></div></div>`).join("")}
        </div>
      </div>
    </section>
  `);
}

async function showStaffRegs() {
  const data = await api("/api/staff-registrations?limit=120");
  openModal("Xodim so'rovlari", `
    <div class="toolbar"><button class="primary-btn" data-open="staff_reg">${icon("plus")} Ro'yxatdan o'tish</button></div>
    <div class="list">${(data.items || []).map((r) => `
      <div class="list-item">
        <div class="list-row"><span class="list-title">#${Number(r.id)} · ${fmt(r.full_name)}</span><span class="pill ${pillClass(r.status)}">${fmt(r.status)}</span></div>
        <div class="meta">${fmt(r.position || r.role)} · ${fmt(r.branch_name || r.branch_actual_name)} · ${fmt(r.phone)}</div>
        ${(state.me.permissions.hr || state.me.permissions.lead) && r.status === "new" ? `
          <div class="button-row">
            <button class="secondary-btn" data-sreg-action="approve" data-id="${Number(r.id)}">Tasdiqlash</button>
            <button class="danger-btn" data-sreg-action="reject" data-id="${Number(r.id)}">Rad etish</button>
          </div>` : ""}
      </div>
    `).join("") || `<div class="empty">Xodim so'rovi yo'q.</div>`}</div>
  `);
  modal.querySelectorAll("[data-open]").forEach((btn) => btn.addEventListener("click", () => openCreate(btn.dataset.open)));
  modal.querySelectorAll("[data-sreg-action]").forEach((btn) => btn.addEventListener("click", () => staffRegAction(btn.dataset.id, btn.dataset.sregAction)));
}

async function staffRegAction(id, action) {
  try {
    const body = { id: Number(id), action };
    if (action === "reject") body.reason = prompt("Rad etish sababi") || "";
    await api("/api/staff-registrations/action", { method: "POST", body });
    toast("Xodim so'rovi yangilandi");
    await loadMe();
    showStaffRegs();
  } catch (err) {
    toast(err.message, true);
  }
}

async function showInterviews() {
  const data = await api("/api/interviews?limit=120");
  openModal("Suhbatlar", `
    <div class="list">${(data.items || []).map((i) => `
      <div class="list-item">
        <div class="list-row"><span class="list-title">${fmt(i.full_name)} · ${fmt(i.date)} ${fmt(i.time, "")}</span><span class="pill ${pillClass(i.status)}">${fmt(i.status)}</span></div>
        <div class="meta">${fmt(i.position)} · ${fmt(i.branch_name)} · ${fmt(i.location)} · kelish: ${fmt(i.attendance)}</div>
        <div class="button-row">
          ${state.me.permissions.hr ? `<button class="secondary-btn" data-int-action="came" data-id="${Number(i.id)}">Keldi</button><button class="danger-btn" data-int-action="absent" data-id="${Number(i.id)}">Kelmadi</button>` : ""}
          <button class="ghost-btn" data-int-action="confirm" data-id="${Number(i.id)}">Tasdiqlash</button>
          <button class="ghost-btn" data-int-action="reschedule" data-id="${Number(i.id)}">Boshqa vaqt</button>
        </div>
      </div>
    `).join("") || `<div class="empty">Suhbat yo'q.</div>`}</div>
  `);
  modal.querySelectorAll("[data-int-action]").forEach((btn) => btn.addEventListener("click", () => interviewAction(btn.dataset.id, btn.dataset.intAction)));
}

async function interviewAction(id, action) {
  try {
    const body = { id: Number(id), action };
    if (action === "reschedule") body.comment = prompt("Qulay vaqt") || "";
    await api("/api/interviews/action", { method: "POST", body });
    toast("Suhbat yangilandi");
    showInterviews();
  } catch (err) {
    toast(err.message, true);
  }
}

async function showFinance() {
  const data = await api("/api/finance");
  openModal("Moliya", `
    <div class="toolbar"><a class="ghost-btn" href="/api/export/employees" target="_blank">${icon("download")} Xodim CSV</a></div>
    <div class="list">${(data.items || []).map((e) => `
      <div class="list-item">
        <div class="list-row"><span class="list-title">${fmt(e.full_name)}</span><span class="pill">${fmt(e.monthly_salary, "Oylik yo'q")}</span></div>
        <div class="meta">${fmt(e.branch_name)} · jarima ${Number(e.fines_total || 0)} · dori ${Number(e.medicines_total || 0)} · kesim ${Number(e.deductions_total || 0)} · ${fmt(e.payment_status, "berilmagan")}</div>
        <div class="button-row">
          <button class="secondary-btn" data-fin-action="set_salary" data-id="${Number(e.user_id)}">Oylik</button>
          <button class="danger-btn" data-fin-action="fine" data-id="${Number(e.user_id)}">Jarima</button>
          <button class="ghost-btn" data-fin-action="medicine" data-id="${Number(e.user_id)}">Dori</button>
          <button class="ghost-btn" data-fin-action="deduction" data-id="${Number(e.user_id)}">Kesish</button>
          <button class="secondary-btn" data-fin-action="paid" data-id="${Number(e.user_id)}">Berildi</button>
        </div>
      </div>
    `).join("") || `<div class="empty">Moliya ma'lumoti yo'q.</div>`}</div>
  `);
  modal.querySelectorAll("[data-fin-action]").forEach((btn) => btn.addEventListener("click", () => financeAction(btn.dataset.id, btn.dataset.finAction)));
}

async function financeAction(userId, action) {
  const body = { user_id: Number(userId), action };
  if (action === "set_salary" || action === "fine" || action === "medicine") body.amount = prompt("Summa") || "";
  if (action === "fine" || action === "medicine") body.reason = prompt("Izoh") || "";
  if (action === "deduction") body.percent = Number(prompt("Foiz", "5") || 5);
  try {
    await api("/api/finance/action", { method: "POST", body });
    toast("Moliya amali bajarildi");
    showFinance();
  } catch (err) {
    toast(err.message, true);
  }
}

async function showAdvance() {
  const data = await api("/api/advance");
  openModal("Avans", `
    <div class="toolbar"><button class="primary-btn" data-open="advance">${icon("plus")} Avans so'rash</button></div>
    <div class="list">${(data.items || []).map((a) => `
      <div class="list-item">
        <div class="list-row"><span class="list-title">${fmt(a.full_name)} · ${Number(a.amount || 0).toLocaleString("uz-UZ")}</span><span class="pill ${pillClass(a.status)}">${fmt(a.status)}</span></div>
        <div class="meta">${fmt(a.period)} · karta ${fmt(a.card_number)} · ${fmt(a.branch_name)}</div>
        ${state.me.permissions.finance || state.me.permissions.hr ? `<div class="button-row"><button class="secondary-btn" data-adv-status="confirmed" data-id="${Number(a.id)}">Tasdiq</button><button class="danger-btn" data-adv-status="declined" data-id="${Number(a.id)}">Rad</button></div>` : ""}
      </div>
    `).join("") || `<div class="empty">Avans so'rovi yo'q.</div>`}</div>
  `);
  modal.querySelectorAll("[data-open]").forEach((btn) => btn.addEventListener("click", () => openCreate(btn.dataset.open)));
  modal.querySelectorAll("[data-adv-status]").forEach((btn) => btn.addEventListener("click", () => advanceAction(btn.dataset.id, btn.dataset.advStatus)));
}

async function advanceAction(id, status) {
  try {
    await api("/api/advance/action", { method: "POST", body: { id: Number(id), status } });
    toast("Avans yangilandi");
    showAdvance();
  } catch (err) {
    toast(err.message, true);
  }
}

async function showTech() {
  const data = await api("/api/tech");
  openModal("Texnik ishlar", `
    <div class="toolbar"><button class="primary-btn" data-open="tech">${icon("plus")} Topshiriq</button></div>
    <div class="list">${(data.items || []).map((t) => `
      <div class="list-item">
        <div class="list-row"><span class="list-title">#${Number(t.id)} · ${fmt(t.title)}</span><span class="pill ${t.priority === "urgent" ? "bad" : pillClass(t.status)}">${fmt(t.status)}</span></div>
        <div class="meta">${fmt(t.branch_name)} · ${fmt(t.category)} · ${fmt(t.tech_name || "texnik belgilanmagan")} · muddat ${fmt(t.deadline_at || t.deadline)}</div>
        <div class="button-row">
          ${state.me.permissions.hr ? `<button class="secondary-btn" data-tech-action="assign" data-id="${Number(t.id)}">Tarqatish</button>` : ""}
          ${state.me.role === "tech" || state.me.permissions.hr ? `<button class="secondary-btn" data-tech-action="accept" data-id="${Number(t.id)}">Qabul</button><button class="ghost-btn" data-tech-action="done" data-id="${Number(t.id)}">Tugatdim</button>` : ""}
          ${state.me.permissions.hr ? `<button class="danger-btn" data-tech-action="close" data-id="${Number(t.id)}">Yopish</button>` : ""}
        </div>
      </div>
    `).join("") || `<div class="empty">Texnik topshiriq yo'q.</div>`}</div>
  `);
  modal.querySelectorAll("[data-open]").forEach((btn) => btn.addEventListener("click", () => openCreate(btn.dataset.open)));
  modal.querySelectorAll("[data-tech-action]").forEach((btn) => btn.addEventListener("click", () => techAction(btn.dataset.id, btn.dataset.techAction)));
}

async function techAction(id, action) {
  const body = { id: Number(id), action };
  if (action === "done") body.cost = Number(prompt("Xarajat (so'm)", "0") || 0);
  try {
    await api("/api/tech/action", { method: "POST", body });
    toast("Texnik topshiriq yangilandi");
    showTech();
  } catch (err) {
    toast(err.message, true);
  }
}

async function showSettings() {
  try {
    const data = await api("/api/settings");
    openModal("Sozlamalar", `
      <form class="form-grid" id="settingsForm">
        ${(data.items || []).map((s) => `<label><span>${fmt(s.key)}</span><input name="${fmt(s.key)}" value="${fmt(s.value, "")}" /></label>`).join("") || `<div class="empty full">Sozlama yo'q.</div>`}
        <label><span>Yangi kalit</span><input name="__new_key" /></label>
        <label><span>Yangi qiymat</span><input name="__new_value" /></label>
        <button class="primary-btn full" type="submit">Saqlash</button>
      </form>
    `);
    $("#settingsForm", modal).addEventListener("submit", saveSettings);
  } catch (err) {
    toast(err.message, true);
  }
}

async function saveSettings(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget).entries());
  if (data.__new_key) data[data.__new_key] = data.__new_value || "";
  delete data.__new_key;
  delete data.__new_value;
  try {
    await api("/api/settings", { method: "PATCH", body: data });
    toast("Sozlamalar saqlandi");
    modal.close();
  } catch (err) {
    toast(err.message, true);
  }
}

async function updateUserRole(id) {
  const role = prompt("Rol (admin/hr/manager/employee/pharmacist/director/accountant/it/tech/candidate)");
  if (!role) return;
  const branch = prompt("Filial ID (bo'sh qoldirish mumkin)") || "";
  try {
    await api(`/api/users/${id}`, { method: "PATCH", body: { role, branch_id: branch || null } });
    toast("Foydalanuvchi yangilandi");
    await loadMe();
    showAdmin();
  } catch (err) {
    toast(err.message, true);
  }
}

async function toggleUserBlock(id, unblock) {
  try {
    await api(`/api/users/${id}`, { method: "PATCH", body: { blocked: unblock ? 0 : 1 } });
    toast("Blok holati yangilandi");
    await loadMe();
    showAdmin();
  } catch (err) {
    toast(err.message, true);
  }
}

function openModal(title, body) {
  modal.innerHTML = `
    <div class="modal-body">
      <div class="modal-head">
        <h2>${escapeHtml(title)}</h2>
        <button class="icon-btn" data-close aria-label="Yopish"><svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
      </div>
      ${body}
    </div>
  `;
  modal.querySelector("[data-close]").addEventListener("click", () => modal.close());
  modal.showModal();
}

function branchOptions(selected = "") {
  return state.ref.branches.map((b) => `<option value="${Number(b.id)}" ${String(selected) === String(b.id) ? "selected" : ""}>${fmt(b.name)}</option>`).join("");
}

function positionOptions(selected = "") {
  return state.ref.positions.map((p) => `<option value="${fmt(p.name)}" ${String(selected) === String(p.name) ? "selected" : ""}>${fmt(p.name)}</option>`).join("");
}

function openCreate(kind, defaults = {}) {
  const forms = {
    application: {
      title: "Ishga ariza",
      html: `
        <form class="form-grid" data-submit="application">
          <input type="hidden" name="vacancy_id" value="${defaults.vacancy_id || ""}" />
          <label><span>Ism-familiya</span><input name="full_name" required value="${fmt(state.me.full_name, "")}" /></label>
          <label><span>Telefon</span><input name="phone" required value="${fmt(state.me.phone, "")}" /></label>
          <label><span>Filial</span><select name="branch_id"><option value="">Tanlang</option>${branchOptions()}</select></label>
          <label><span>Lavozim</span><select name="position"><option value="">Tanlang</option>${positionOptions()}</select></label>
          <label><span>Tug'ilgan sana</span><input name="birth_date" placeholder="kun.oy.yil" /></label>
          <label><span>Smena</span><input name="shift" /></label>
          <label><span>Kutilayotgan maosh</span><input name="expected_salary" /></label>
          <label><span>Tajriba</span><input name="exp_years" /></label>
          <label class="full"><span>Manzil</span><input name="address" /></label>
          <label class="full"><span>Sabab</span><textarea name="reason"></textarea></label>
          <button class="primary-btn full" type="submit">Yuborish</button>
        </form>`,
    },
    vacancy: {
      title: "Vakansiya",
      html: `
        <form class="form-grid" data-submit="vacancy">
          <label><span>Lavozim</span><input name="title" required /></label>
          <label><span>Filial</span><select name="branch_id">${branchOptions(state.me.branch_id)}</select></label>
          <label><span>Smena</span><input name="shift" /></label>
          <label><span>Oylik</span><input name="salary" /></label>
          <label><span>Ish vaqti</span><input name="work_time" /></label>
          <label><span>Soni</span><input name="staff_count" /></label>
          <label class="full"><span>Talablar</span><textarea name="requirements"></textarea></label>
          <label class="full"><span>Sharoit</span><textarea name="conditions"></textarea></label>
          <button class="primary-btn full" type="submit">Saqlash</button>
        </form>`,
    },
    dayoff: {
      title: "Dam kunini almashtirish",
      html: `
        <form class="form-grid" data-submit="request" data-kind="dayoff">
          <label><span>Hozirgi dam kuni</span><input name="from_day" value="${fmt(state.profile?.rest_day, "")}" /></label>
          <label><span>Yangi dam kuni</span><input name="to_day" required /></label>
          <label class="full"><span>Sabab</span><textarea name="reason" required></textarea></label>
          <button class="primary-btn full" type="submit">Yuborish</button>
        </form>`,
    },
    work_hours: {
      title: "Ish vaqtini o'zgartirish",
      html: `
        <form class="form-grid" data-submit="request" data-kind="work_hours">
          <label class="full"><span>Yangi ish vaqti</span><input name="requested_hours" placeholder="09:00 - 18:00" required /></label>
          <button class="primary-btn full" type="submit">Yuborish</button>
        </form>`,
    },
    salary: {
      title: "Maosh oshirish",
      html: `
        <form class="form-grid" data-submit="request" data-kind="salary">
          <label class="full"><span>So'ralgan summa</span><input name="requested_amount" required /></label>
          <button class="primary-btn full" type="submit">Yuborish</button>
        </form>`,
    },
    branch_transfer: {
      title: "Filial almashtirish",
      html: `
        <form class="form-grid" data-submit="request" data-kind="branch_transfer">
          <label class="full"><span>Yangi filial</span><select name="to_branch_id" required>${branchOptions()}</select></label>
          <button class="primary-btn full" type="submit">Yuborish</button>
        </form>`,
    },
    hr_message: {
      title: "HR ga murojaat",
      html: `
        <form class="form-grid" data-submit="request" data-kind="hr_message">
          <label class="full"><span>Mavzu</span><input name="subject" /></label>
          <label class="full"><span>Xabar</span><textarea name="message" required></textarea></label>
          <button class="primary-btn full" type="submit">Yuborish</button>
        </form>`,
    },
    manager_request: {
      title: "Rahbar so'rovi",
      html: `
        <form class="form-grid" data-submit="request" data-kind="manager_request">
          <label><span>Turi</span><select name="kind"><option value="vacancy">Xodim kerak</option><option value="technical">Texnik nosozlik</option><option value="other">Boshqa</option></select></label>
          <label><span>Filial</span><select name="branch_id">${branchOptions(state.me.branch_id)}</select></label>
          <label><span>Mavzu</span><input name="title" required /></label>
          <label><span>Soni</span><input name="staff_count" /></label>
          <label><span>Smena</span><input name="shift" /></label>
          <label><span>Tajriba</span><input name="experience" /></label>
          <label class="full"><span>Izoh</span><textarea name="details"></textarea></label>
          <button class="primary-btn full" type="submit">Yuborish</button>
        </form>`,
    },
    notification: {
      title: "Bildirishnoma",
      html: `
        <form class="form-grid" data-submit="notification">
          <label><span>Kimga</span><select name="target_type"><option value="all">Barchaga</option><option value="role">Rol</option><option value="branch">Filial</option><option value="user">Bitta xodim</option></select></label>
          <label><span>Qiymat</span><input name="target_value" placeholder="role, branch id yoki user id" /></label>
          <label class="full"><span>Sarlavha</span><input name="title" required /></label>
          <label class="full"><span>Xabar</span><textarea name="body"></textarea></label>
          <button class="primary-btn full" type="submit">Yuborish</button>
        </form>`,
    },
    branch: {
      title: "Filial qo'shish",
      html: `
        <form class="form-grid" data-submit="branch">
          <label><span>Nomi</span><input name="name" required /></label>
          <label><span>Telefon</span><input name="phone" /></label>
          <label class="full"><span>Manzil</span><input name="address" /></label>
          <label><span>Latitude</span><input name="latitude" /></label>
          <label><span>Longitude</span><input name="longitude" /></label>
          <label><span>Radius</span><input name="radius" value="150" /></label>
          <label><span>Ish vaqti</span><input name="work_hours" placeholder="08:00 - 24:00" /></label>
          <button class="primary-btn full" type="submit">Saqlash</button>
        </form>`,
    },
    staff_reg: {
      title: "Gulnora Farm xodimi",
      html: `
        <form class="form-grid" data-submit="staff_reg">
          <label><span>Ism-familiya</span><input name="full_name" required value="${fmt(state.me.full_name, "")}" /></label>
          <label><span>Telefon</span><input name="phone" value="${fmt(state.me.phone, "")}" /></label>
          <label><span>Tug'ilgan sana</span><input name="birth_date" placeholder="kun.oy.yil" /></label>
          <label><span>Ota/ona telefoni</span><input name="parent_phone" /></label>
          <label><span>Rol</span><select name="role">${state.ref.roles.map((r) => `<option value="${fmt(r.value)}">${fmt(r.label)}</option>`).join("")}</select></label>
          <label><span>Lavozim</span><select name="position"><option value="">Tanlang</option>${positionOptions()}</select></label>
          <label><span>Filial</span><select name="branch_id">${branchOptions(state.me.branch_id)}</select></label>
          <label><span>Ish vaqti</span><input name="work_hours" placeholder="09:00 - 18:00" /></label>
          <label><span>Oylik</span><input name="salary" /></label>
          <label><span>Dam kuni</span><input name="rest_day" /></label>
          <label><span>Forma</span><select name="uniform_status"><option value="yes">Bor</option><option value="no">Yo'q</option><option value="unknown">Noma'lum</option></select></label>
          <label><span>Ma'lumot</span><input name="education" /></label>
          <label class="full"><span>Manzil</span><input name="address" /></label>
          <label class="full"><span>Qo'shimcha</span><textarea name="extra_info"></textarea></label>
          <button class="primary-btn full" type="submit">HR ga yuborish</button>
        </form>`,
    },
    advance: {
      title: "Avans so'rash",
      html: `
        <form class="form-grid" data-submit="advance">
          <label><span>Summa</span><input name="amount" required /></label>
          <label><span>Karta raqami</span><input name="card_number" required /></label>
          <button class="primary-btn full" type="submit">Yuborish</button>
        </form>`,
    },
    tech: {
      title: "Texnik topshiriq",
      html: `
        <form class="form-grid" data-submit="tech">
          <label><span>Mavzu</span><input name="title" required /></label>
          <label><span>Filial</span><select name="branch_id">${branchOptions(state.me.branch_id)}</select></label>
          <label><span>Kategoriya</span><select name="category"><option>Elektr</option><option>Suv/santexnika</option><option>Mebel</option><option>Texnika/kompyuter</option><option>Konditsioner</option><option>Ta'mir/qurilish</option><option>Boshqa</option></select></label>
          <label><span>Daraja</span><select name="priority"><option value="normal">Oddiy</option><option value="urgent">Shoshilinch</option></select></label>
          <label><span>Muddat</span><input name="deadline" /></label>
          <label><span>Muddat sana</span><input name="deadline_at" type="date" /></label>
          <label class="full"><span>Izoh</span><textarea name="details"></textarea></label>
          <button class="primary-btn full" type="submit">Yuborish</button>
        </form>`,
    },
    position: {
      title: "Lavozim qo'shish",
      html: `
        <form class="form-grid" data-submit="position">
          <label class="full"><span>Lavozim nomi</span><input name="name" required /></label>
          <button class="primary-btn full" type="submit">Saqlash</button>
        </form>`,
    },
  };
  const form = forms[kind];
  if (!form) return;
  openModal(form.title, form.html);
  const el = modal.querySelector("form");
  el.addEventListener("submit", submitCreate);
}

async function submitCreate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const body = Object.fromEntries(new FormData(form).entries());
  const submit = form.dataset.submit;
  if (form.dataset.kind) body.kind = form.dataset.kind;
  try {
    if (submit === "application") await api("/api/applications", { method: "POST", body });
    if (submit === "vacancy") await api("/api/vacancies", { method: "POST", body });
    if (submit === "request") await api("/api/requests", { method: "POST", body });
    if (submit === "notification") await api("/api/notifications", { method: "POST", body });
    if (submit === "branch") await api("/api/admin/branches", { method: "POST", body });
    if (submit === "staff_reg") await api("/api/staff-registrations", { method: "POST", body });
    if (submit === "advance") await api("/api/advance", { method: "POST", body });
    if (submit === "tech") await api("/api/tech", { method: "POST", body });
    if (submit === "position") await api("/api/positions/action", { method: "POST", body: { ...body, action: "add" } });
    modal.close();
    toast("Saqlandi");
    await loadMe();
    await render();
  } catch (err) {
    toast(err.message, true);
  }
}

boot();
