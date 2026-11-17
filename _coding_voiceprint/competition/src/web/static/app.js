const state = { intakeMode: "customer", refreshTimer: null, data: {}, user: null };

const titles = {
  overview: "运行总览", intake: "录音处理", jobs: "任务中心",
  customers: "客户声纹库", black: "黑产声纹库", clusters: "团伙声纹簇",
  reviews: "人工复核", models: "模型与阈值", monitoring: "运行监控",
  accounts: "账号管理", permissions: "权限配置", releases: "版本公告",
};
const permissionLabels = {
  view_customer_key: "查看客户主键", view_audio: "播放录音", view_transcript: "查看ASR文本",
  view_embedding_metadata: "查看声纹元数据", manage_users: "管理账号", manage_permissions: "管理权限",
  manage_releases: "发布公告", view_monitoring: "查看监控", trigger_cluster: "运行N:N",
};

const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[char]);

const shortId = value => value ? `${String(value).slice(0, 13)}…` : "--";
const number = (value, digits = 3) => value === null || value === undefined ? "--" : Number(value).toFixed(digits);
const timeText = value => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "--";
const statusText = value => ({
  queued: "排队", processing: "处理中", completed: "完成", failed: "失败",
  review_required: "待复核", active: "有效", pending: "待审核",
  pending_enrollment: "待建库", approved: "已通过", rejected: "已拒绝",
  identified: "已判角", role_identified: "已判角", external_review: "外部复核",
  rolled_out: "滚动出库", disabled: "停用", shadow: "影子",
})[value] || value || "--";
const badge = value => `<span class="badge status-${escapeHtml(value)}">${escapeHtml(statusText(value))}</span>`;
const emptyRow = (columns, text = "暂无数据") => `<tr><td class="empty" colspan="${columns}">${text}</td></tr>`;

async function api(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", ...options });
  const content = await response.json().catch(() => ({}));
  if (response.status === 401) showLogin();
  if (!response.ok) throw new Error(content.error || `HTTP ${response.status}`);
  return content;
}

function showLogin() {
  state.user = null;
  document.querySelector("#loginScreen").hidden = false;
  clearTimeout(state.refreshTimer);
}

function hideLogin(user) {
  state.user = user;
  document.querySelector("#loginScreen").hidden = true;
  document.querySelector("#currentUser").textContent = `${user.display_name || user.username} · ${user.role}`;
  applyPermissions();
}

function can(permission) {
  return Boolean(state.user?.permissions?.[permission]);
}

function applyPermissions() {
  document.querySelector('[data-view="accounts"]').hidden = !can("manage_users");
  document.querySelector('[data-view="permissions"]').hidden = !can("manage_permissions");
  document.querySelector('[data-view="releases"]').hidden = !can("manage_releases");
  document.querySelector('[data-view="monitoring"]').hidden = !can("view_monitoring");
  document.querySelector("#runClusterButton").disabled = !can("trigger_cluster");
}

function toast(message, type = "normal") {
  const element = document.querySelector("#toast");
  element.textContent = message;
  element.dataset.type = type;
  element.hidden = false;
  clearTimeout(element.timer);
  element.timer = setTimeout(() => { element.hidden = true; }, 3200);
}

function navigate(view) {
  document.querySelectorAll(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.view === view));
  document.querySelectorAll(".view").forEach(item => item.classList.toggle("active", item.dataset.viewPanel === view));
  document.querySelector("#pageTitle").textContent = titles[view] || "声纹风险工作台";
  if (view === "intake") document.querySelector("#identityInput").focus();
}

function setIntakeMode(mode) {
  state.intakeMode = mode;
  document.querySelectorAll("[data-intake]").forEach(button => button.classList.toggle("active", button.dataset.intake === mode));
  document.querySelector("#identityLabel span").textContent = mode === "customer" ? "客户主键" : "黑产身份主键";
  document.querySelector("#identityInput").name = mode === "customer" ? "customer_key" : "actor_key";
  document.querySelector("#reviewerField").hidden = mode !== "black";
  document.querySelector("#submitButton").textContent = mode === "customer" ? "上传并核验" : "提交黑产审核";
}

function renderOverview(overview, jobs) {
  document.querySelector("#metricJobs").textContent = overview.jobs.total;
  document.querySelector("#metricJobState").textContent = `${overview.jobs.queued}排队 · ${overview.jobs.processing}处理中`;
  document.querySelector("#metricCustomers").textContent = overview.active_customer_templates;
  document.querySelector("#metricCustomerState").textContent = `${overview.customers}个客户`;
  document.querySelector("#metricBlack").textContent = overview.black_templates;
  document.querySelector("#metricBlackState").textContent = `${overview.black_actors}个黑产身份`;
  document.querySelector("#metricReviews").textContent = overview.pending_reviews;
  document.querySelector("#navPending").textContent = overview.pending_reviews;
  document.querySelector("#backendName").textContent = overview.models.backend_version;
  document.querySelector("#roleModel").textContent = overview.models.role_model_version;
  document.querySelector("#qualityThreshold").textContent = number(overview.models.quality_threshold, 4);
  document.querySelector("#blackThreshold").textContent = number(overview.models.black_search.threshold, 4);
  document.querySelector("#recentJobs").innerHTML = jobs.slice(0, 7).map(job => `
    <tr class="clickable" data-recording="${escapeHtml(job.recording_id)}">
      <td title="${escapeHtml(job.id)}">${shortId(job.id)}</td><td>${job.kind === "black_enrollment" ? "黑产入库" : "客户核验"}</td>
      <td>${escapeHtml(statusText(job.stage))}</td><td><div class="progress"><i style="width:${Number(job.progress || 0)}%"></i></div></td>
      <td>${badge(job.status)}</td><td>${timeText(job.created_at)}</td>
    </tr>`).join("") || emptyRow(6);
}

function renderJobs(items) {
  document.querySelector("#jobRows").innerHTML = items.map(job => `
    <tr class="clickable" data-recording="${escapeHtml(job.recording_id)}">
      <td title="${escapeHtml(job.id)}">${shortId(job.id)}</td><td>${job.kind === "black_enrollment" ? "黑产入库" : "客户核验"}</td>
      <td>${escapeHtml(statusText(job.stage))}</td><td><div class="progress"><i style="width:${Number(job.progress || 0)}%"></i></div></td>
      <td>${badge(job.status)}</td><td>${job.result_id ? shortId(job.result_id) : "--"}</td><td>${timeText(job.created_at)}</td>
    </tr>`).join("") || emptyRow(7);
}

function renderCustomers(items) {
  document.querySelector("#customerRows").innerHTML = items.map(row => `
    <tr class="clickable" data-customer="${escapeHtml(row.id)}"><td>${escapeHtml(row.customer_key || row.cust_no || "--")}</td><td title="${escapeHtml(row.id)}">${shortId(row.id)}</td><td>${badge(row.status)}</td>
      <td>${row.active_template_count}</td><td>${row.pending_template_count}</td><td>${timeText(row.updated_at)}</td></tr>`).join("") || emptyRow(6);
}

function renderBlack(items) {
  document.querySelector("#blackRows").innerHTML = items.map(row => `
    <tr class="clickable" data-black="${escapeHtml(row.id)}"><td>${escapeHtml(row.id)}</td><td>${badge(row.status)}</td>
      <td>${row.active_template_count}</td><td>${timeText(row.updated_at)}</td></tr>`).join("") || emptyRow(4);
}

function renderClusters(items) {
  document.querySelector("#clusterRows").innerHTML = items.map(row => `
    <tr><td title="${escapeHtml(row.id)}">${shortId(row.id)}</td><td>${row.customer_count}</td><td>${row.edge_count}</td>
      <td>${row.clusters.length}</td><td>${number(row.threshold)}</td><td>${row.shadow_only ? badge("shadow") : badge(row.status)}</td><td>${timeText(row.created_at)}</td></tr>`).join("") || emptyRow(7);
}

function renderReviews(items) {
  document.querySelector("#reviewRows").innerHTML = items.map(row => `
    <tr><td><span class="priority priority-${escapeHtml(row.priority)}">${escapeHtml(row.priority)}</span></td><td>${escapeHtml(row.kind)}</td>
      <td class="reason">${escapeHtml(row.reason)}</td><td title="${escapeHtml(row.target_id)}">${shortId(row.target_id)}</td><td>${badge(row.status)}</td>
      <td>${row.status === "pending" ? `<div class="row-actions"><button data-review="${row.id}" data-decision="approve">通过</button><button class="danger" data-review="${row.id}" data-decision="reject">拒绝</button></div>` : "--"}</td></tr>`).join("") || emptyRow(6);
}

function renderModels(model) {
  document.querySelector("#modelDetails").innerHTML = `
    <div><dt>角色识别</dt><dd>${escapeHtml(model.role_model_version)}</dd></div>
    <div><dt>Embedding</dt><dd>${escapeHtml(model.embedding_model_version)}</dd></div>
    <div><dt>打分后端</dt><dd>${escapeHtml(model.backend_version)}</dd></div>
    <div><dt>PLDA维度</dt><dd>${model.plda_dimension}</dd></div>`;
  document.querySelector("#selfThresholds").innerHTML = `
    <div><dt>拒绝阈值</dt><dd>&lt; ${number(model.self_check.reject_below)}</dd></div>
    <div><dt>灰区</dt><dd>${number(model.self_check.reject_below)} 至 ${number(model.self_check.accept_at_or_above)}</dd></div>
    <div><dt>通过阈值</dt><dd>≥ ${number(model.self_check.accept_at_or_above)}</dd></div>`;
  document.querySelector("#blackDetails").innerHTML = `
    <div><dt>打分方式</dt><dd>${escapeHtml(model.black_search.backend)}</dd></div>
    <div><dt>命中阈值</dt><dd>${number(model.black_search.threshold, 4)}</dd></div>
    <div><dt>返回数量</dt><dd>Top-${model.black_search.topk}</dd></div>`;
}

function dlRows(values) {
  return Object.entries(values).map(([key, value]) => `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
}

function renderMonitoring(monitor) {
  if (!monitor) return;
  document.querySelector("#monitorService").innerHTML = dlRows({
    运行模式: monitor.service.mode,
    Worker: monitor.service.worker_alive ? "运行中" : "未启动",
    生成时间: timeText(monitor.generated_at),
  });
  document.querySelector("#monitorJobs").innerHTML = dlRows({
    总任务: monitor.jobs.total,
    排队: monitor.jobs.queued,
    处理中: monitor.jobs.processing,
    失败: monitor.jobs.failed,
    外部复核录音: monitor.recordings.external_review,
    待流转复核: monitor.reviews.pending,
  });
  document.querySelector("#monitorStorage").innerHTML = dlRows({
    总字节: monitor.storage.bytes,
    上传文件: monitor.storage.uploads,
    处理产物: monitor.storage.artifacts,
    向量文件: monitor.storage.vectors,
    客户滚动出库: monitor.templates.customer_rolled_out,
  });
}

function renderUsers(items) {
  const body = document.querySelector("#userRows");
  if (!body) return;
  body.innerHTML = items.map(row => `<tr><td>${escapeHtml(row.username)}</td><td>${escapeHtml(row.display_name)}</td><td>${escapeHtml(row.role)}</td><td>${badge(row.status)}</td><td>${timeText(row.last_login_at)}</td></tr>`).join("") || emptyRow(5);
}

function renderPermissions(policy) {
  const form = document.querySelector("#permissionForm");
  if (!form || !policy) return;
  const roles = ["admin", "operator", "viewer"];
  const keys = Object.keys(permissionLabels);
  form.innerHTML = `
    <div class="permission-grid">
      <b>权限</b>${roles.map(role => `<b>${role}</b>`).join("")}
      ${keys.map(key => `<span>${permissionLabels[key]}</span>${roles.map(role => `<label><input type="checkbox" data-permission="${key}" data-role="${role}" ${policy.roles?.[role]?.[key] ? "checked" : ""}>启用</label>`).join("")}`).join("")}
    </div>
    <div class="form-actions"><button class="primary-button" type="submit">保存权限</button><span id="permissionSaveState"></span></div>`;
}

function renderReleases(items) {
  const list = document.querySelector("#releaseRows");
  if (!list) return;
  list.innerHTML = items.map(row => `<article class="release-item"><h3>${escapeHtml(row.version)} · ${escapeHtml(row.title)}</h3><p>${escapeHtml(row.body)}</p><small>${escapeHtml(row.created_by || "--")} · ${timeText(row.created_at)}</small></article>`).join("") || "<div class=\"notice\">暂无公告</div>";
}

async function refresh(silent = false) {
  try {
    const requests = [
      api("/api/v1/overview"), api("/api/v1/jobs"), api("/api/v1/customers"),
      api("/api/v1/black-actors"), api("/api/v1/cluster-runs"), api("/api/v1/reviews"), api("/api/v1/models"),
    ];
    if (can("view_monitoring")) requests.push(api("/api/v1/admin/monitoring")); else requests.push(Promise.resolve(null));
    if (can("manage_users")) requests.push(api("/api/v1/admin/users")); else requests.push(Promise.resolve({ items: [] }));
    if (can("manage_permissions")) requests.push(api("/api/v1/admin/access-policy")); else requests.push(Promise.resolve(null));
    requests.push(api("/api/v1/admin/releases"));
    const [overview, jobs, customers, black, clusters, reviews, models, monitor, users, policy, releases] = await Promise.all(requests);
    state.data = { overview, jobs: jobs.items, customers: customers.items, black: black.items, clusters: clusters.items, reviews: reviews.items, models };
    renderOverview(overview, jobs.items); renderJobs(jobs.items); renderCustomers(customers.items);
    renderBlack(black.items); renderClusters(clusters.items); renderReviews(reviews.items); renderModels(models);
    renderMonitoring(monitor); renderUsers(users.items); renderPermissions(policy); renderReleases(releases.items);
    document.querySelector("#serviceDot").className = "online";
    document.querySelector("#serviceText").textContent = "本地服务正常";
    document.querySelector("#refreshTime").textContent = `更新于 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;
    document.querySelector("#errorBanner").hidden = true;
    clearTimeout(state.refreshTimer);
    const busy = overview.jobs.queued + overview.jobs.processing > 0;
    state.refreshTimer = setTimeout(() => refresh(true), busy ? 2500 : 10000);
  } catch (error) {
    document.querySelector("#serviceDot").className = "offline";
    document.querySelector("#serviceText").textContent = "服务连接失败";
    const banner = document.querySelector("#errorBanner");
    banner.textContent = error.message; banner.hidden = false;
    if (!silent) toast(error.message, "error");
    clearTimeout(state.refreshTimer); state.refreshTimer = setTimeout(() => refresh(true), 5000);
  }
}

async function showRecording(recordingId) {
  if (!recordingId) return;
  try {
    const recording = await api(`/api/v1/recordings/${recordingId}`);
    const requests = [recording.transcript_available ? api(`/api/v1/recordings/${recordingId}/transcript`) : Promise.resolve(null)];
    if (recording.verification_id) requests.push(api(`/api/v1/verifications/${recording.verification_id}`));
    const [transcript, verification] = await Promise.all(requests);
    document.querySelector("#detailType").textContent = recording.kind === "black_enrollment" ? "黑产入库" : "客户核验";
    document.querySelector("#detailTitle").textContent = shortId(recording.id);
    const role = recording.role || {};
    const labels = verification?.labels || [];
    document.querySelector("#detailBody").innerHTML = `
      <div class="detail-summary"><div><span>状态</span>${badge(recording.status)}</div><div><span>客户声道</span><strong>${escapeHtml(role.customer_ch || "--")}</strong></div><div><span>角色置信</span><strong>${escapeHtml(role.confidence || "--")}</strong></div><div><span>质量分</span><strong>${number(recording.quality?.score, 4)}</strong></div></div>
      <div class="label-row">${labels.length ? labels.map(item => `<b>${escapeHtml(item)}</b>`).join("") : "<span>无风险标签</span>"}</div>
      ${recording.channels_available?.length ? `<div class="audio-grid"><label>原始录音<audio controls preload="none" src="/api/v1/recordings/${recording.id}/audio/original"></audio></label><label>左声道<audio controls preload="none" src="/api/v1/recordings/${recording.id}/audio/L"></audio></label><label>右声道<audio controls preload="none" src="/api/v1/recordings/${recording.id}/audio/R"></audio></label></div>` : ""}
      ${transcript && !transcript.expired ? `<div class="transcript-grid"><section><span>左声道 ASR</span><p>${escapeHtml(transcript.left || "无转写")}</p></section><section><span>右声道 ASR</span><p>${escapeHtml(transcript.right || "无转写")}</p></section></div>` : ""}
      ${verification ? `<div class="score-grid"><section><span>客户1:1</span><strong>${escapeHtml(verification.self_check.status)}</strong><small>分数 ${number(verification.self_check.score)}</small></section><section><span>黑产1:N</span><strong>${escapeHtml(verification.black_search.status)}</strong><small>Top-1 ${number(verification.black_search.topk?.[0]?.score, 4)}</small></section></div>` : ""}`;
    document.querySelector("#detailDialog").showModal();
  } catch (error) { toast(error.message, "error"); }
}

async function showLibraryDetail(kind, id) {
  try {
    const data = await api(kind === "customer" ? `/api/v1/customers/${id}` : `/api/v1/black-actors/${id}`);
    document.querySelector("#detailType").textContent = kind === "customer" ? "客户声纹" : "黑产声纹";
    document.querySelector("#detailTitle").textContent = kind === "customer" ? (data.customer_key || data.cust_no || data.id) : data.id;
    document.querySelector("#detailBody").innerHTML = `
      <div class="detail-summary"><div><span>状态</span>${badge(data.status)}</div>${kind === "customer" ? `<div><span>客户主键</span><strong>${escapeHtml(data.customer_key || data.cust_no || "--")}</strong></div>` : ""}<div><span>有效模板</span><strong>${data.active_template_count}</strong></div><div><span>更新时间</span><strong>${timeText(data.updated_at)}</strong></div></div>
      <div class="table-scroll"><table><thead><tr><th>模板</th><th>状态</th><th>来源录音</th><th>原始录音</th><th>创建时间</th></tr></thead><tbody>${data.templates.map(item => `<tr><td>${shortId(item.id)}</td><td>${badge(item.status)}</td><td>${shortId(item.recording_id)}</td><td>${escapeHtml(item.source_recording_id || "--")}</td><td>${timeText(item.created_at)}</td></tr>`).join("") || emptyRow(5)}</tbody></table></div>`;
    document.querySelector("#detailDialog").showModal();
  } catch (error) { toast(error.message, "error"); }
}

document.addEventListener("click", async event => {
  const nav = event.target.closest("[data-view]"); if (nav) navigate(nav.dataset.view);
  const go = event.target.closest("[data-go]"); if (go) { navigate(go.dataset.go); if (go.dataset.mode) setIntakeMode(go.dataset.mode); }
  const mode = event.target.closest("[data-intake]"); if (mode) setIntakeMode(mode.dataset.intake);
  const recording = event.target.closest("[data-recording]"); if (recording) showRecording(recording.dataset.recording);
  const customer = event.target.closest("[data-customer]"); if (customer) showLibraryDetail("customer", customer.dataset.customer);
  const black = event.target.closest("[data-black]"); if (black) showLibraryDetail("black", black.dataset.black);
  const review = event.target.closest("[data-review]");
  if (review) {
    try {
      await api(`/api/v1/reviews/${review.dataset.review}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: review.dataset.decision, reviewer: document.querySelector("#decisionReviewer").value }) });
      toast(review.dataset.decision === "approve" ? "已通过" : "已拒绝"); refresh(true);
    } catch (error) { toast(error.message, "error"); }
  }
});

document.querySelector("#loginForm").addEventListener("submit", async event => {
  event.preventDefault();
  const error = document.querySelector("#loginError");
  error.hidden = true;
  try {
    const result = await api("/api/v1/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.querySelector("#loginUsername").value,
        password: document.querySelector("#loginPassword").value,
      }),
    });
    hideLogin(result.user);
    refresh(true);
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  }
});

document.querySelector("#logoutButton").addEventListener("click", async () => {
  await api("/api/v1/logout", { method: "POST" }).catch(() => null);
  showLogin();
});

document.querySelector("#uploadForm").addEventListener("submit", async event => {
  event.preventDefault();
  const audio = document.querySelector("#audioInput").files[0];
  if (!audio) return toast("请选择录音文件", "error");
  const form = new FormData(); form.append("audio", audio);
  const identity = document.querySelector("#identityInput").value.trim();
  form.append(state.intakeMode === "customer" ? "customer_key" : "actor_key", identity);
  if (state.intakeMode === "black") form.append("reviewer", document.querySelector("#reviewerInput").value);
  const button = document.querySelector("#submitButton"); button.disabled = true; document.querySelector("#uploadState").textContent = "正在上传";
  try {
    const result = await api(state.intakeMode === "customer" ? "/api/v1/recordings" : "/api/v1/black-recordings", { method: "POST", body: form });
    toast(`任务已创建 ${shortId(result.id)}`); event.target.reset(); setIntakeMode(state.intakeMode); navigate("jobs"); refresh(true);
  } catch (error) { toast(error.message, "error"); }
  finally { button.disabled = false; document.querySelector("#uploadState").textContent = ""; }
});

document.querySelector("#audioInput").addEventListener("change", event => {
  const file = event.target.files[0]; document.querySelector("#fileName").textContent = file?.name || "选择双轨录音";
  if (file) document.querySelector("#fileMeta").textContent = `${(file.size / 1024 / 1024).toFixed(2)} MiB · ${file.type || "音频文件"}`;
});

document.querySelector("#runClusterButton").addEventListener("click", async () => {
  try { const run = await api("/api/v1/cluster-runs", { method: "POST" }); toast(`N:N完成，候选簇 ${run.clusters.length}`); refresh(true); }
  catch (error) { toast(error.message, "error"); }
});
document.querySelector("#userForm").addEventListener("submit", async event => {
  event.preventDefault();
  const payload = {
    username: document.querySelector("#userNameInput").value.trim(),
    display_name: document.querySelector("#displayNameInput").value.trim(),
    role: document.querySelector("#roleInput").value,
    status: document.querySelector("#statusInput").value,
    password: document.querySelector("#passwordInput").value,
  };
  try {
    await api("/api/v1/admin/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    document.querySelector("#passwordInput").value = "";
    toast("账号已保存"); refresh(true);
  } catch (error) { toast(error.message, "error"); }
});
document.querySelector("#permissionForm").addEventListener("submit", async event => {
  event.preventDefault();
  const roles = { admin: {}, operator: {}, viewer: {} };
  document.querySelectorAll("[data-permission][data-role]").forEach(input => {
    roles[input.dataset.role][input.dataset.permission] = input.checked;
  });
  try {
    await api("/api/v1/admin/access-policy", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ roles }) });
    toast("权限已保存"); refresh(true);
  } catch (error) { toast(error.message, "error"); }
});
document.querySelector("#releaseForm").addEventListener("submit", async event => {
  event.preventDefault();
  const payload = {
    version: document.querySelector("#releaseVersion").value.trim(),
    title: document.querySelector("#releaseTitle").value.trim(),
    body: document.querySelector("#releaseBody").value.trim(),
  };
  try {
    await api("/api/v1/admin/releases", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    event.target.reset(); toast("公告已发布"); refresh(true);
  } catch (error) { toast(error.message, "error"); }
});
document.querySelector("#refreshButton").addEventListener("click", () => refresh());
document.querySelector("#closeDialog").addEventListener("click", () => document.querySelector("#detailDialog").close());

function drawSignal() {
  const canvas = document.querySelector("#signalCanvas"), ratio = window.devicePixelRatio || 1;
  const width = Math.max(canvas.clientWidth, 240), height = canvas.clientHeight;
  canvas.width = width * ratio; canvas.height = height * ratio;
  const ctx = canvas.getContext("2d"); ctx.scale(ratio, ratio); ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = "#6a8e8b"; ctx.lineWidth = 1.4; ctx.beginPath();
  for (let x = 0; x <= width; x += 3) { const y = height / 2 + Math.sin(x * .11) * Math.sin(x * .027) * 23; x ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
  ctx.stroke();
}

window.addEventListener("resize", drawSignal);
async function init() {
  setIntakeMode("customer"); drawSignal();
  const session = await api("/api/v1/session").catch(() => ({ user: null }));
  if (session.user) {
    hideLogin(session.user);
    refresh();
  } else {
    showLogin();
  }
}
init();
