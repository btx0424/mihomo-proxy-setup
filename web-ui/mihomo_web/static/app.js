async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function showMsg(text, ok = true) {
  const el = document.getElementById("action-msg");
  el.hidden = false;
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "err");
}

async function loadStatus() {
  const data = await api("/api/status");
  const out = document.getElementById("status-out");
  const parts = [data.stdout, data.stderr].filter(Boolean).join("\n");
  out.textContent = parts || "(empty)";
  await loadBinaryStatus();
}

async function loadBinaryStatus() {
  const el = document.getElementById("binary-line");
  const btn = document.getElementById("btn-binary-update");
  try {
    const b = await api("/api/binary");
    if (b.error) {
      el.textContent = `Mihomo binary: v${b.installed_version || "?"} — latest lookup failed (${b.error})`;
      btn.disabled = false;
      btn.title = "Retry download metadata";
      return;
    }
    const latest = b.latest_version ? `v${b.latest_version}` : "?";
    const inst = b.installed_version ? `v${b.installed_version}` : "?";
    el.textContent = b.update_available
      ? `Mihomo binary: ${inst} → latest ${latest} (update available)`
      : `Mihomo binary: ${inst} (up to date with ${latest})`;
    btn.disabled = false;
    btn.title = b.update_available ? "Download and install latest release" : "Re-install latest release";
  } catch (e) {
    el.textContent = "Mihomo binary: " + e.message;
  }
}

async function updateMihomoBinary() {
  const btn = document.getElementById("btn-binary-update");
  if (!confirm("Download latest mihomo from GitHub and restart the daemon if it is running?")) {
    return;
  }
  btn.disabled = true;
  btn.textContent = "Updating…";
  try {
    const data = await api("/api/binary/update?restart=true", { method: "POST" });
    showMsg(data.message || "Update finished", true);
    await loadStatus();
    await loadBinaryStatus();
  } catch (e) {
    showMsg("Update: " + e.message, false);
  } finally {
    btn.disabled = false;
    btn.textContent = "Update mihomo";
  }
}

async function runAction(path, label, btn) {
  if (btn) btn.disabled = true;
  try {
    const data = await api(path, { method: "POST" });
    const parts = [data.stdout, data.stderr].filter(Boolean).join("\n");
    showMsg(label + (parts ? ": " + parts.split("\n")[0] : ""), data.ok);
    await loadStatus();
    await refreshSelection();
  } catch (e) {
    showMsg(label + " failed: " + e.message, false);
  } finally {
    if (btn) btn.disabled = false;
  }
}

let groupsCache = [];

async function loadGroups() {
  try {
    const data = await api("/api/groups");
    groupsCache = data.groups || [];
  } catch {
    groupsCache = [{ name: "PROXY", type: "Selector", now: "" }];
  }
  const sel = document.getElementById("group-select");
  const current = sel.value || "PROXY";
  sel.innerHTML = "";
  const names = groupsCache.length ? groupsCache.map((g) => g.name) : ["PROXY"];
  for (const name of names) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    sel.appendChild(opt);
  }
  if (names.includes(current)) sel.value = current;
  else sel.value = names[0];
}

function selectedGroup() {
  return document.getElementById("group-select").value || "PROXY";
}

async function refreshNow() {
  try {
    const data = await api("/api/now?group=" + encodeURIComponent(selectedGroup()));
    const line = data.chain.map((c) => `${c.group} → ${c.now || "?"}`).join("  ·  ");
    document.getElementById("now-line").textContent = line || "—";
  } catch (e) {
    document.getElementById("now-line").textContent = e.message;
  }
}

async function loadNodes() {
  const ul = document.getElementById("node-list");
  ul.innerHTML = "";
  try {
    const data = await api("/api/nodes?group=" + encodeURIComponent(selectedGroup()));
    document.getElementById("now-line").textContent =
      `${data.group} → ${data.now || "?"}`;
    for (const m of data.members) {
      const li = document.createElement("li");
      if (m.current) li.classList.add("current");
      const span = document.createElement("span");
      span.className = "name";
      span.textContent = (m.current ? "* " : "  ") + m.name;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "Select";
      btn.addEventListener("click", () => selectNode(m.name));
      li.append(span, btn);
      ul.appendChild(li);
    }
  } catch (e) {
    const li = document.createElement("li");
    li.textContent = e.message;
    ul.appendChild(li);
  }
}

async function selectNode(node) {
  try {
    const data = await api("/api/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group: selectedGroup(), node }),
    });
    showMsg(`Selected ${data.group} → ${data.now}`, true);
    await loadNodes();
    await loadGroups();
  } catch (e) {
    showMsg(e.message, false);
  }
}

async function runBench() {
  const btn = document.getElementById("btn-bench");
  btn.disabled = true;
  btn.textContent = "Bench running…";
  const box = document.getElementById("bench-results");
  box.hidden = true;
  try {
    const data = await api("/api/bench?group=" + encodeURIComponent(selectedGroup()), {
      method: "POST",
    });
    const tbody = document.getElementById("bench-tbody");
    tbody.innerHTML = "";
    data.ok.forEach((row, i) => {
      const tr = document.createElement("tr");
      if (row.current) tr.classList.add("current");
      tr.innerHTML = `<td>${i + 1}</td><td>${row.delay_ms}</td><td>${escapeHtml(row.name)}</td><td></td>`;
      const td = tr.lastElementChild;
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = "Use";
      b.className = "ghost";
      b.addEventListener("click", () => selectNode(row.name));
      td.appendChild(b);
      tbody.appendChild(tr);
    });
    const s = data.summary;
    document.getElementById("bench-summary").textContent =
      `${s.ok} ok / ${s.fail} fail / ${s.total} total` +
      (data.fastest ? ` · fastest: ${data.fastest.name} (${data.fastest.delay_ms} ms)` : "");
    box.hidden = false;
    await loadNodes();
  } catch (e) {
    showMsg("Bench: " + e.message, false);
  } finally {
    btn.disabled = false;
    btn.textContent = "Bench (latency)";
  }
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}

async function loadLog() {
  const data = await api("/api/log?lines=100");
  document.getElementById("log-out").textContent = data.text || "(empty)";
}

async function loadSubscription() {
  const tbody = document.getElementById("subscription-tbody");
  try {
    const data = await api("/api/subscription");
    tbody.innerHTML = "";
    if (!data.providers?.length) {
      tbody.innerHTML = "<tr><td colspan=\"4\">No subscription providers (is mihomo running?)</td></tr>";
      return;
    }
    for (const p of data.providers) {
      const tr = document.createElement("tr");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ghost";
      btn.textContent = "Refresh";
      btn.addEventListener("click", () => refreshSubscription([p.name]));
      tr.innerHTML = `<td>${escapeHtml(p.name)}</td><td>${escapeHtml(p.age_human)}</td><td>${p.proxy_count}</td><td></td>`;
      tr.lastElementChild.appendChild(btn);
      tbody.appendChild(tr);
    }
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4">${escapeHtml(e.message)}</td></tr>`;
  }
}

async function refreshSubscription(names) {
  const btnAll = document.getElementById("btn-subscription-refresh");
  btnAll.disabled = true;
  btnAll.textContent = "Refreshing…";
  try {
    await api("/api/subscription/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ providers: names || [] }),
    });
    await loadSubscription();
    showMsg(names?.length === 1 ? `Refreshed ${names[0]}` : "Refreshed all providers", true);
  } catch (e) {
    showMsg("Refresh: " + e.message, false);
  } finally {
    btnAll.disabled = false;
    btnAll.textContent = "Refresh all";
  }
}

async function loadProxySnippets() {
  const data = await api("/api/proxy-snippets");
  document.getElementById("proxy-on").textContent = data.on_shell.trim();
  document.getElementById("copy-on").onclick = () =>
    copyText(data.on_shell, "Copied proxy-on exports");
  document.getElementById("copy-off").onclick = () =>
    copyText(data.off_shell, "Copied proxy-off");
}

async function copyText(text, okMsg) {
  try {
    await navigator.clipboard.writeText(text.trim());
    showMsg(okMsg, true);
  } catch {
    showMsg("Clipboard failed — select text manually", false);
  }
}

async function refreshSelection() {
  await loadGroups();
  await loadNodes();
}

async function runUsageCheck() {
  const btn = document.getElementById("btn-check");
  const direct = document.getElementById("check-direct").checked;
  btn.disabled = true;
  btn.textContent = "Checking…";
  const table = document.getElementById("check-table");
  const summaryEl = document.getElementById("check-summary");
  table.hidden = true;
  summaryEl.hidden = true;
  try {
    const q = direct ? "?direct=true" : "";
    const data = await api("/api/check" + q, { method: "POST" });
    const tbody = document.getElementById("check-tbody");
    tbody.innerHTML = "";
    for (const r of data.results) {
      const tr = document.createElement("tr");
      let badge = "fail";
      let stat = "FAIL";
      if (r.skipped) {
        badge = "skip";
        stat = "SKIP";
      } else if (r.ok) {
        badge = "ok";
        stat = "OK";
      }
      const time =
        r.latency_ms != null ? `${r.latency_ms} ms` : "—";
      const detail = r.skipped
        ? r.error || ""
        : r.error || (r.status ? `HTTP ${r.status}` : "");
      tr.innerHTML = `<td><span class="badge ${badge}">${stat}</span></td><td>${time}</td><td>${escapeHtml(r.label)}</td><td>${escapeHtml(detail)}</td>`;
      tbody.appendChild(tr);
    }
    const s = data.summary;
    const via = data.direct ? "direct" : data.proxy || "proxy";
    summaryEl.textContent = `${via}: ${s.ok} ok / ${s.fail} fail / ${s.skipped} skipped · ${data.elapsed_ms} ms wall`;
    table.hidden = false;
    summaryEl.hidden = false;
    showMsg(s.fail ? "Some checks failed" : "All checks passed", s.fail === 0);
  } catch (e) {
    showMsg("Check: " + e.message, false);
  } finally {
    btn.disabled = false;
    btn.textContent = "Run check";
  }
}

document.getElementById("btn-refresh-status").onclick = () => loadStatus().catch((e) => showMsg(e.message, false));
document.getElementById("btn-start").onclick = (e) =>
  runAction("/api/start", "Start", e.currentTarget);
document.getElementById("btn-stop").onclick = (e) =>
  runAction("/api/stop", "Stop", e.currentTarget);
document.getElementById("btn-restart").onclick = (e) =>
  runAction("/api/restart", "Restart", e.currentTarget);
document.getElementById("btn-test").onclick = (e) =>
  runAction("/api/test", "Test", e.currentTarget);
document.getElementById("btn-binary-update").onclick = () => updateMihomoBinary();
document.getElementById("btn-reload-nodes").onclick = () => refreshSelection();
document.getElementById("btn-bench").onclick = () => runBench();
document.getElementById("btn-check").onclick = () => runUsageCheck();
document.getElementById("btn-subscription-reload").onclick = () => loadSubscription();
document.getElementById("btn-subscription-refresh").onclick = () => refreshSubscription([]);
document.getElementById("btn-reload-log").onclick = () => loadLog().catch((e) => showMsg(e.message, false));
document.getElementById("group-select").onchange = () => {
  loadNodes();
  refreshNow();
};

(async () => {
  await loadProxySnippets();
  await loadStatus();
  await loadSubscription();
  await refreshSelection();
  await loadLog();
})();
