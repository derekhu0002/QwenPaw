const fallbackConfig = window.SECURITY_CENTER_CONFIG || {};
const injectedApiBase = (fallbackConfig.apiBase || "").replace(/\/$/, "");
const storedApiBase = (localStorage.getItem("security-center-api-base") || "").replace(/\/$/, "");
const defaultApiBase = "http://127.0.0.1:8091";
const state = {
  apiBase: injectedApiBase || storedApiBase || defaultApiBase,
  overview: null,
  selectedClientId: null,
  stream: null,
};

const elements = {
  apiBase: document.getElementById("api-base"),
  apiConfig: document.getElementById("api-config"),
  apiStatus: document.getElementById("api-status"),
  metricGrid: document.getElementById("metric-grid"),
  trustView: document.getElementById("trust-view"),
  rejectionView: document.getElementById("rejection-view"),
  voucherView: document.getElementById("voucher-view"),
  timelineChart: document.getElementById("timeline-chart"),
  handshakeProgress: document.getElementById("handshake-progress"),
  clientSelect: document.getElementById("client-select"),
  alertTitle: document.getElementById("alert-title"),
  alertLatency: document.getElementById("alert-latency"),
  eventLog: document.getElementById("event-log"),
  eventLogMirror: document.getElementById("event-log-mirror"),
  toast: document.getElementById("toast"),
};

const TRUST_STATE_LABELS = {
  UNKNOWN: "未知",
  ALIGNED: "已对齐",
  DIVERGED: "已分叉",
  GAP_VALIDATION_REQUIRED: "缺口待验证",
  UNTRUSTED: "不可信",
  REJECTED: "已拒绝",
};

const ALERT_TYPE_LABELS = {
  AUDIT_LOCKDOWN: "审计锁定",
  SECURITY_REJECTION: "安全拒绝",
};

elements.apiBase.value = state.apiBase;

function rememberApiBase(value) {
  state.apiBase = value.replace(/\/$/, "");
  localStorage.setItem("security-center-api-base", state.apiBase);
  elements.apiBase.value = state.apiBase;
}

elements.apiConfig.addEventListener("submit", async (event) => {
  event.preventDefault();
  rememberApiBase(elements.apiBase.value);
  await refreshDashboard();
});

elements.clientSelect.addEventListener("change", async (event) => {
  state.selectedClientId = event.target.value || null;
  await renderTimeline();
});

function apiUrl(path) {
  return `${state.apiBase}${path}`;
}

function trustLabel(value) {
  return TRUST_STATE_LABELS[value] || value || "未知";
}

function alertTypeLabel(value) {
  return ALERT_TYPE_LABELS[value] || value || "未分类告警";
}

async function readJson(path) {
  const response = await fetch(apiUrl(path));
  if (!response.ok) {
    throw new Error(`${path} failed: ${response.status}`);
  }
  return await response.json();
}

function metricCard(label, value, tone = "") {
  return `<div class="metric-card ${tone}"><div class="metric-label">${label}</div><div class="metric-value">${value}</div></div>`;
}

function stackCard(title, body, tone = "") {
  return `<div class="stack-card ${tone}"><strong>${title}</strong><div>${body}</div></div>`;
}

function setApiStatus(message, tone = "") {
  elements.apiStatus.textContent = message;
  elements.apiStatus.className = `api-status ${tone}`.trim();
}

function updateMetrics(overview) {
  elements.metricGrid.innerHTML = [
    metricCard("接入客户端", overview.client_count ?? 0),
    metricCard("拒绝事件", overview.rejection_count ?? 0, "warning"),
    metricCard("不可信恢复", overview.lockdown_count ?? 0, "danger"),
    metricCard("实时告警", (overview.alerts || []).length, "success"),
  ].join("");
}

function updateTrustView(overview) {
  const clients = overview.clients || [];
  if (!clients.length) {
    elements.trustView.innerHTML = stackCard("暂无客户端状态", "等待第一条边缘上报进入安全中心。", "warning");
    return;
  }
  elements.trustView.innerHTML = clients
    .map((client) => {
      const trust = client.trust_state || "UNKNOWN";
      const tone = trust === "UNTRUSTED"
        ? "danger"
        : trust === "ALIGNED"
          ? "success"
          : trust === "GAP_VALIDATION_REQUIRED"
            ? "warning"
            : "";
      return stackCard(
        client.client_id,
        `信任状态：<span class="${tone}">${trustLabel(trust)}</span><br/>Gap 状态：${client.gap_status || "CLEAR"}<br/>恢复闸门：${client.recovery_gate_status || "CLOSED"}<br/>最近 trace：${client.last_trace_id || "--"}`,
        tone,
      );
    })
    .join("");
}

function updateRejectionView(overview) {
  const rejections = overview.rejections || [];
  if (!rejections.length) {
    elements.rejectionView.innerHTML = stackCard("暂无拒绝事件", "等待 Security_Rejection_Nonce 上报。", "warning");
    elements.voucherView.textContent = "尚未捕获拒绝凭证。";
    return;
  }
  const latest = rejections[rejections.length - 1];
  elements.rejectionView.innerHTML = rejections
    .slice()
    .reverse()
    .map((record) => stackCard(record.tool_name, `Nonce：${record.nonce}<br/>客户端：${record.client_id}`, "danger"))
    .join("");
  elements.voucherView.innerHTML = `
    <div>
      <strong>Security_Rejection_Nonce 凭证</strong>
      <span class="voucher-code">${latest.voucher}</span>
      <div>Trace：${latest.trace_id}</div>
    </div>
  `;
}

function updateClientPicker(overview) {
  const clients = overview.clients || [];
  const options = clients
    .map((client) => `<option value="${client.client_id}">${client.client_id}</option>`)
    .join("");
  elements.clientSelect.innerHTML = options || '<option value="">暂无客户端</option>';
  if (!state.selectedClientId || !clients.some((client) => client.client_id === state.selectedClientId)) {
    state.selectedClientId = clients[0]?.client_id || null;
  }
  elements.clientSelect.value = state.selectedClientId || "";
}

function hashToCoordinate(hash, minY, maxY) {
  if (!hash) {
    return maxY;
  }
  const value = parseInt(hash.slice(0, 8), 16);
  const ratio = value / 0xffffffff;
  return maxY - (maxY - minY) * ratio;
}

function drawPolyline(points, color) {
  return `<polyline fill="none" stroke="${color}" stroke-width="4" points="${points.map((point) => `${point.x},${point.y}`).join(" ")}" />`;
}

function drawTimeline(timeline) {
  const width = 640;
  const height = 260;
  const padding = 40;
  const local = timeline.local_hash_curve || [];
  const cloud = timeline.cloud_shadow_curve || [];
  const maxLength = Math.max(local.length, cloud.length, 2);
  const xForIndex = (index) => padding + ((width - padding * 2) / (maxLength - 1 || 1)) * index;
  const minY = 32;
  const maxY = height - 34;
  const localPoints = local.map((point, index) => ({ x: xForIndex(index), y: hashToCoordinate(point.hash, minY, maxY) }));
  const cloudPoints = cloud.map((point, index) => ({ x: xForIndex(index), y: hashToCoordinate(point.hash, minY, maxY) }));
  const fork = timeline.fork_point;
  const forkIndex = fork ? Number(fork.sequence || 0) : null;
  const forkX = forkIndex !== null ? xForIndex(forkIndex) : null;
  const forkY = fork ? hashToCoordinate(fork.local_hash || fork.cloud_shadow_hash, minY, maxY) : null;
  elements.timelineChart.innerHTML = `
    <rect x="0" y="0" width="640" height="260" rx="18" fill="rgba(255,255,255,0.02)" />
    <line x1="40" y1="220" x2="600" y2="220" stroke="rgba(255,255,255,0.12)" />
    <line x1="40" y1="32" x2="40" y2="220" stroke="rgba(255,255,255,0.12)" />
    ${drawPolyline(localPoints, "#ff7a3d")}
    ${drawPolyline(cloudPoints, "#4bc1ff")}
    ${forkX !== null ? `<circle cx="${forkX}" cy="${forkY}" r="7" fill="#ff4f6d" /><text x="${forkX + 12}" y="${forkY - 12}" fill="#ff4f6d" font-size="12">分叉点 ${fork.event_id}</text>` : ""}
    <text x="48" y="24" fill="#ff7a3d" font-size="12">本地哈希</text>
    <text x="150" y="24" fill="#4bc1ff" font-size="12">云侧影子哈希</text>
  `;
}

async function renderTimeline() {
  if (!state.selectedClientId) {
    elements.handshakeProgress.innerHTML = stackCard("尚未选择客户端", "当安全中心收到上报后，请在右上角选择一个客户端。", "warning");
    drawTimeline({ local_hash_curve: [], cloud_shadow_curve: [], fork_point: null });
    return;
  }
  try {
    const timeline = await readJson(`/security-center/v1/operator/timelines/${encodeURIComponent(state.selectedClientId)}`);
    drawTimeline(timeline);
    const trustTone = timeline.trust_state === "UNTRUSTED"
      ? "danger"
      : timeline.trust_state === "ALIGNED"
        ? "success"
        : timeline.trust_state === "GAP_VALIDATION_REQUIRED"
          ? "warning"
          : "";
    elements.handshakeProgress.innerHTML = [
      stackCard("恢复握手进度", `需要恢复：${timeline.recovery_required ? "是" : "否"}`),
      stackCard("当前信任态", trustLabel(timeline.trust_state || "UNKNOWN"), trustTone),
      stackCard("Gap 校验状态", timeline.gap_status || "CLEAR", timeline.gap_status === "GAP_VALIDATION_REQUIRED" ? "warning" : ""),
      stackCard("恢复闸门", timeline.recovery_gate_status || "CLOSED", timeline.recovery_gate_status === "OPEN" ? "danger" : "success"),
      stackCard(
        "最后可信锚点",
        `序号：${timeline.last_trusted_sequence ?? 0}<br/>事件：${timeline.last_trusted_anchor_event_id || "--"}`,
      ),
      stackCard(
        "当前边缘申报头",
        `序号：${timeline.current_edge_reported_sequence ?? 0}<br/>事件：${timeline.current_edge_reported_anchor_event_id || "--"}`,
      ),
      stackCard("分叉点", timeline.fork_point ? timeline.fork_point.event_id : "暂无分叉"),
    ].join("");
  } catch (error) {
    elements.handshakeProgress.innerHTML = stackCard("时间线不可用", error.message, "danger");
  }
}

function createEventLogItem(alert) {
  const item = document.createElement("div");
  item.className = "event-item";
  item.innerHTML = `<strong>${alertTypeLabel(alert.type)}</strong><div>${alert.message}</div><div>${alert.client_id || "--"}</div>`;
  return item;
}

function trimEventLog(container, limit = 12) {
  while (container.children.length > limit) {
    container.removeChild(container.lastChild);
  }
}

function appendEventLog(alert) {
  if (elements.eventLog) {
    elements.eventLog.prepend(createEventLogItem(alert));
    trimEventLog(elements.eventLog, 6);
  }
  if (elements.eventLogMirror) {
    elements.eventLogMirror.prepend(createEventLogItem(alert));
    trimEventLog(elements.eventLogMirror, 12);
  }
}

function renderEventLogs(alerts) {
  const sortedAlerts = (alerts || []).slice().reverse();
  if (elements.eventLog) {
    elements.eventLog.innerHTML = "";
  }
  if (elements.eventLogMirror) {
    elements.eventLogMirror.innerHTML = "";
  }
  if (!sortedAlerts.length) {
    const emptyState = createEventLogItem({
      type: "SYSTEM",
      message: "当前未收到实时运营事件。",
      client_id: "等待流式告警",
    });
    if (elements.eventLog) {
      elements.eventLog.append(emptyState.cloneNode(true));
    }
    if (elements.eventLogMirror) {
      elements.eventLogMirror.append(emptyState);
    }
    return;
  }
  sortedAlerts.forEach((alert) => appendEventLog(alert));
}

function showToast(alert) {
  elements.toast.innerHTML = `<strong>${alertTypeLabel(alert.type)}</strong><div>${alert.message}</div>`;
  elements.toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    elements.toast.classList.add("hidden");
  }, 4200);
}

function updateAlertState(alert) {
  elements.alertTitle.textContent = alert.message;
  if (alert.edge_timestamp_ns) {
    const latency = Math.max(0, Math.round(Date.now() - Number(alert.edge_timestamp_ns) / 1_000_000));
    elements.alertLatency.textContent = `${latency} ms`;
  } else if (alert.alert_latency_ms !== undefined) {
    elements.alertLatency.textContent = `${alert.alert_latency_ms} ms`;
  }
  appendEventLog(alert);
  showToast(alert);
}

function connectStream() {
  if (state.stream) {
    state.stream.close();
  }
  const stream = new EventSource(apiUrl("/security-center/v1/operator/stream"));
  stream.addEventListener("ready", () => setApiStatus("实时告警流已连接。", "success"));
  stream.addEventListener("security-alert", async (event) => {
    const alert = JSON.parse(event.data);
    updateAlertState(alert);
    await refreshDashboard(false);
  });
  stream.onerror = () => setApiStatus("实时告警流已断开，正在自动重连。", "danger");
  state.stream = stream;
}

async function refreshDashboard(reconnectStream = true) {
  try {
    const overview = await readJson("/security-center/v1/operator/overview");
    state.overview = overview;
    updateMetrics(overview);
    updateTrustView(overview);
    updateRejectionView(overview);
    renderEventLogs(overview.alerts || []);
    updateClientPicker(overview);
    await renderTimeline();
    setApiStatus("已连接到安全中心后端。", "success");
    if (reconnectStream) {
      connectStream();
    }
  } catch (error) {
    const fallbackCandidates = [injectedApiBase, defaultApiBase].filter(
      (candidate) => candidate && candidate !== state.apiBase,
    );
    for (const candidate of fallbackCandidates) {
      try {
        rememberApiBase(candidate);
        const overview = await readJson("/security-center/v1/operator/overview");
        state.overview = overview;
        updateMetrics(overview);
        updateTrustView(overview);
        updateRejectionView(overview);
        renderEventLogs(overview.alerts || []);
        updateClientPicker(overview);
        await renderTimeline();
        setApiStatus(`已通过 ${state.apiBase} 恢复后端连接。`, "success");
        if (reconnectStream) {
          connectStream();
        }
        return;
      } catch {
        // Try the next fallback candidate.
      }
    }
    setApiStatus(`${error.message}（当前 API 地址：${state.apiBase}）`, "danger");
  }
}

refreshDashboard();
