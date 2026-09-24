"use strict";

// Browser controls for the local simulator's probe capture API. This is a
// software analyzer over reconstructed nets, not a Vivado Hardware Manager IP.
(() => {
  const $ = (id) => document.getElementById(id);
  const svgNS = "http://www.w3.org/2000/svg";
  const colors = ["#168c9b", "#256fbb", "#3a9e75", "#d19b25", "#8a6cb4", "#d47a64"];
  let ready = false;
  let designHash = null;
  let catalog = [];
  let byId = new Map();
  let chosen = [];
  let capture = null;
  let busy = false;
  let polling = false;
  let lastWaveSignature = "";

  async function request(path, payload) {
    const response = await fetch(path, payload === undefined ? undefined : {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data?.error || `Request failed (${response.status})`);
    return data;
  }

  function showError(message) {
    $("logic-error").textContent = message || "";
    $("logic-error").hidden = !message;
  }

  function label(id) { return byId.get(id)?.label || id; }

  function updateTriggerSource() {
    const select = $("logic-trigger-probe");
    const previous = select.value;
    select.replaceChildren();
    for (const id of chosen) {
      const option = document.createElement("option");
      option.value = id;
      option.textContent = label(id);
      select.appendChild(option);
    }
    if (chosen.includes(previous)) select.value = previous;
    select.disabled = !ready || $("logic-trigger-mode").value === "immediate" || !chosen.length;
  }

  function renderChosen() {
    const list = $("logic-probes");
    list.replaceChildren();
    for (const [index, id] of chosen.entries()) {
      const row = document.createElement("div");
      row.className = "logic-probe";
      const dot = document.createElement("span");
      dot.className = "logic-probe-dot";
      dot.style.backgroundColor = colors[index % colors.length];
      const name = document.createElement("span");
      name.className = "logic-probe-name";
      name.title = label(id);
      name.textContent = label(id);
      const group = document.createElement("span");
      group.className = "logic-probe-group";
      group.textContent = byId.get(id)?.group || "";
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "logic-remove";
      remove.setAttribute("aria-label", `Remove ${label(id)}`);
      remove.textContent = "×";
      remove.addEventListener("click", () => {
        chosen = chosen.filter(item => item !== id);
        renderChosen(); searchCatalog();
      });
      row.append(dot, name, group, remove);
      list.appendChild(row);
    }
    $("logic-probe-count").textContent = `${chosen.length} / 16`;
    updateTriggerSource();
    updateButtons();
  }

  function searchCatalog() {
    const list = $("logic-search-results");
    list.replaceChildren();
    const query = $("logic-probe-search").value.trim().toLowerCase();
    if (!ready) return;
    const matches = catalog.filter(item => !chosen.includes(item.id) &&
      (!query || `${item.label} ${item.group}`.toLowerCase().includes(query))).slice(0, 24);
    for (const item of matches) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "logic-result";
      button.textContent = item.label;
      button.title = `${item.group}: ${item.label}`;
      button.addEventListener("click", () => {
        if (chosen.length >= 16) return showError("A capture can include up to 16 probes.");
        chosen.push(item.id);
        renderChosen(); searchCatalog(); showError("");
      });
      list.appendChild(button);
    }
    if (!matches.length) {
      const empty = document.createElement("span");
      empty.className = "logic-search-empty";
      empty.textContent = query ? "No matching probes" : "No more probes";
      list.appendChild(empty);
    }
  }

  function svgElement(name, attributes = {}) {
    const node = document.createElementNS(svgNS, name);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    return node;
  }

  function drawWaveforms(state) {
    const holder = $("logic-waveform");
    holder.replaceChildren();
    const samples = state?.samples || [];
    if (!samples.length) {
      const empty = document.createElement("div");
      empty.className = "logic-waveform-empty";
      empty.textContent = state?.phase === "waiting" ?
        "Waiting for trigger. Run or step the simulation." :
        "Arm the analyzer or capture now to see clock-by-clock signals.";
      holder.appendChild(empty);
      return;
    }
    const left = 150, row = 36, top = 35;
    const pitch = Math.max(5, Math.min(40,
      Math.floor((Math.max(holder.clientWidth, 400) - left - 32) / samples.length)));
    const width = Math.max(holder.clientWidth, left + samples.length * pitch + 30, 400);
    const height = top + state.probes.length * row + 25;
    const svg = svgElement("svg", {width, height, viewBox: `0 0 ${width} ${height}`,
      role: "img", "aria-label": `Waveforms for ${state.probes.length} probes over ${samples.length} clock cycles`});
    svg.classList.add("logic-svg");
    const span = Math.max(1, Math.ceil(70 / pitch));
    for (let i = 0; i < samples.length; i += span) {
      const x = left + i * pitch;
      svg.appendChild(svgElement("line", {x1:x, y1:top - 12, x2:x, y2:height - 15,
        stroke:"#e6eceb", "stroke-width":1}));
      const tick = svgElement("text", {x, y:18, fill:"#8a9a9f", "font-size":10,
        "font-family":"monospace"});
      tick.textContent = String(samples[i].cycle);
      svg.appendChild(tick);
    }
    const axis = svgElement("text", {x:8, y:18, fill:"#8a9a9f", "font-size":10,
      "font-family":"monospace"});
    axis.textContent = "CLOCK CYCLE";
    svg.appendChild(axis);
    state.probes.forEach((id, index) => {
      const y = top + index * row;
      const name = svgElement("text", {x:8, y:y + 18, fill:"#264653", "font-size":11,
        "font-family":"monospace"});
      name.textContent = label(id).length > 19 ? `${label(id).slice(0, 18)}…` : label(id);
      svg.appendChild(name);
      svg.appendChild(svgElement("line", {x1:left, y1:y + row - 1,
        x2:width - 10, y2:y + row - 1, stroke:"#edf1ef", "stroke-width":1}));
      let path = "";
      let priorY = null;
      for (let sampleIndex = 0; sampleIndex < samples.length; sampleIndex++) {
        const value = samples[sampleIndex].values[index];
        const pointY = value === 1 ? y + 7 : value === 0 ? y + 25 : y + 16;
        const x = left + sampleIndex * pitch;
        if (priorY === null) path += `M${x} ${pointY}`;
        else if (pointY !== priorY) path += `H${x}V${pointY}`;
        priorY = pointY;
      }
      path += `H${left + samples.length * pitch}`;
      svg.appendChild(svgElement("path", {d:path, fill:"none", stroke:colors[index % colors.length],
        "stroke-width":1.8, "stroke-linejoin":"round"}));
    });
    if (state.trigger_index !== null && state.trigger_index < samples.length) {
      const x = left + state.trigger_index * pitch;
      svg.appendChild(svgElement("line", {x1:x, y1:top - 12, x2:x, y2:height - 15,
        stroke:"#d67e55", "stroke-width":1.5, "stroke-dasharray":"4 3"}));
    }
    holder.appendChild(svg);
  }

  function renderCapture(state) {
    capture = state;
    const phase = state?.phase || "unavailable";
    $("logic-status").textContent = phase.toUpperCase();
    $("logic-status").dataset.phase = phase;
    $("logic-sample-count").textContent = `${state?.samples?.length || 0} / ${state?.depth || 0} samples`;
    $("logic-csv").hidden = !state?.samples?.length;
    const signature = `${phase}:${state?.samples?.length || 0}:${state?.samples?.at(-1)?.cycle || 0}:${(state?.probes || []).join("|")}`;
    if (signature !== lastWaveSignature) {
      drawWaveforms(state);
      lastWaveSignature = signature;
    }
    updateButtons();
  }

  function updateButtons() {
    const usable = ready && !busy && chosen.length > 0;
    $("logic-arm").disabled = !usable;
    $("logic-capture").disabled = !usable;
    $("logic-stop").disabled = !ready || busy || !["waiting", "capturing"].includes(capture?.phase);
    $("vio-apply").disabled = !ready || busy;
    $("logic-probe-search").disabled = !ready;
  }

  function configuration(forceImmediate = false) {
    const mode = forceImmediate ? "immediate" : $("logic-trigger-mode").value;
    return {action:"configure", probes:chosen, depth:Number($("logic-depth").value),
      trigger:{mode, probe: mode === "immediate" ? null : $("logic-trigger-probe").value}};
  }

  async function perform(action) {
    if (busy) return;
    busy = true; updateButtons(); showError("");
    try {
      if (action === "stop") {
        renderCapture(await request("/api/logic", {action:"stop"}));
      } else {
        await request("/api/logic", configuration(action === "capture"));
        renderCapture(await request("/api/logic", {action:"arm"}));
        if (action === "capture") {
          let remaining = Number($("logic-depth").value);
          while (remaining > 0) {
            const batch = Math.min(remaining, 1000);
            await window.boardControl({step:batch});
            remaining -= batch;
          }
          renderCapture(await request("/api/logic"));
        }
      }
    } catch (error) { showError(error.message); }
    finally { busy = false; updateButtons(); }
  }

  async function refresh() {
    if (!ready || polling || busy) return;
    polling = true;
    try { renderCapture(await request("/api/logic")); }
    catch (error) { showError(error.message); }
    finally { polling = false; }
  }

  async function boardState(next) {
    const wasReady = ready;
    ready = next.status === "ready";
    if (document.activeElement !== $("vio-word")) {
      const word = next.switches.reduce((value, bit, index) => value | (bit << index), 0);
      $("vio-word").value = `0x${word.toString(16).toUpperCase().padStart(4, "0")}`;
    }
    const leds = next.leds;
    $("vio-led-word").textContent = leds.includes(null) ? "0x----" :
      `0x${leds.reduce((value, bit, index) => value | (bit << index), 0).toString(16).toUpperCase().padStart(4, "0")}`;
    if (!ready) {
      if (wasReady) { designHash = null; catalog = []; byId.clear(); chosen = []; renderChosen(); }
      renderCapture(null); updateButtons();
      return;
    }
    if (next.sha256 && next.sha256 !== designHash) {
      designHash = next.sha256;
      try {
        const [nextCatalog, nextCapture] = await Promise.all([
          request("/api/logic/catalog"), request("/api/logic")]);
        if (next.sha256 !== designHash) return;
        catalog = nextCatalog; byId = new Map(catalog.map(item => [item.id, item]));
        chosen = (nextCapture?.probes || []).filter(id => byId.has(id));
        renderChosen(); searchCatalog(); renderCapture(nextCapture);
      } catch (error) { designHash = null; showError(error.message); }
    }
    updateButtons();
  }

  $("logic-probe-search").addEventListener("input", searchCatalog);
  $("logic-trigger-mode").addEventListener("change", updateTriggerSource);
  $("logic-arm").addEventListener("click", () => perform("arm"));
  $("logic-capture").addEventListener("click", () => perform("capture"));
  $("logic-stop").addEventListener("click", () => perform("stop"));
  $("vio-apply").addEventListener("click", async () => {
    const value = $("vio-word").value.trim().replace(/^0x/i, "");
    if (!/^[\da-f]{1,4}$/i.test(value)) return showError("Enter a 16-bit hexadecimal switch value.");
    try { await window.boardControl({switches:parseInt(value,16)}); showError(""); }
    catch (error) { showError(error.message); }
  });
  $("vio-word").addEventListener("keydown", event => {
    if (event.key === "Enter") $("vio-apply").click();
  });
  document.addEventListener("virtual-board-state", event => boardState(event.detail));
  window.addEventListener("resize", () => {
    lastWaveSignature = "";
    if (capture) renderCapture(capture);
  });
  setInterval(refresh, 400);
  renderCapture(null);
})();
