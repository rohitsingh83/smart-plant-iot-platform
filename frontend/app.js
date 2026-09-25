/**
 * Apex Smart Plant Care - Single-Page Digital Twin Application
 * Handles real-time polling, Chart.js telemetry visualization, actuator commands, and alarm acknowledgement.
 */

let activeDeviceId = "esp32-greenhouse-01";
let telemetryChart = null;
let pollTimer = null;
let historyTimer = null;

// Botanical Presets Mapping
const BOTANICAL_PRESETS = {
  "Tropical Foliage": { min: 50, max: 75, pump: 6, cooldown: 25 },
  "Succulents": { min: 20, max: 35, pump: 4, cooldown: 120 },
  "Vegetables/Tomatoes": { min: 40, max: 65, pump: 7, cooldown: 35 },
  "Culinary Herbs": { min: 35, max: 55, pump: 5, cooldown: 30 }
};

document.addEventListener("DOMContentLoaded", () => {
  initChart();
  setupEventListeners();
  loadDeviceList();
  fetchLatestState();
  fetchHistory();
  fetchAlerts();

  // Periodic polling
  pollTimer = setInterval(fetchLatestState, 2500);
  historyTimer = setInterval(fetchHistory, 7000);
  setInterval(fetchAlerts, 6000);
});

function setupEventListeners() {
  const deviceSelect = document.getElementById("deviceSelect");
  deviceSelect.addEventListener("change", (e) => {
    activeDeviceId = e.target.value;
    fetchLatestState();
    fetchHistory();
  });

  const speciesSelect = document.getElementById("speciesProfileSelect");
  speciesSelect.addEventListener("change", (e) => {
    const profile = BOTANICAL_PRESETS[e.target.value];
    if (profile) {
      document.getElementById("sliderMinMoisture").value = profile.min;
      document.getElementById("sliderMinVal").innerText = `${profile.min}%`;
      document.getElementById("sliderMaxMoisture").value = profile.max;
      document.getElementById("sliderMaxVal").innerText = `${profile.max}%`;
    }
  });

  const sliderMin = document.getElementById("sliderMinMoisture");
  sliderMin.addEventListener("input", (e) => {
    document.getElementById("sliderMinVal").innerText = `${e.target.value}%`;
  });

  const sliderMax = document.getElementById("sliderMaxMoisture");
  sliderMax.addEventListener("input", (e) => {
    document.getElementById("sliderMaxVal").innerText = `${e.target.value}%`;
  });

  document.getElementById("btnSaveConfig").addEventListener("click", saveDeviceConfig);
  document.getElementById("btnManualActuate").addEventListener("click", triggerManualIrrigation);
  document.getElementById("btnRefreshAlerts").addEventListener("click", fetchAlerts);
  document.getElementById("alarmBannerAckBtn").addEventListener("click", ackTopAlarm);
}

function initChart() {
  const ctx = document.getElementById("telemetryChart").getContext("2d");
  telemetryChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Soil Moisture (%)",
          data: [],
          borderColor: "#10b981",
          backgroundColor: "rgba(16, 185, 129, 0.1)",
          fill: true,
          tension: 0.3,
          yAxisID: "yMoisture",
          borderWidth: 2,
          pointRadius: 2
        },
        {
          label: "Temperature (°C)",
          data: [],
          borderColor: "#f59e0b",
          backgroundColor: "transparent",
          tension: 0.3,
          yAxisID: "yTemp",
          borderWidth: 2,
          pointRadius: 2
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false
      },
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          grid: { color: "rgba(51, 65, 85, 0.4)" },
          ticks: { color: "#94a3b8", maxTicksLimit: 8, font: { size: 10 } }
        },
        yMoisture: {
          type: "linear",
          position: "left",
          min: 0,
          max: 100,
          grid: { color: "rgba(51, 65, 85, 0.4)" },
          ticks: { color: "#10b981", font: { size: 10 } }
        },
        yTemp: {
          type: "linear",
          position: "right",
          min: 10,
          max: 45,
          grid: { drawOnChartArea: false },
          ticks: { color: "#f59e0b", font: { size: 10 } }
        }
      }
    }
  });
}

async function loadDeviceList() {
  try {
    const res = await fetch("/api/v1/devices");
    if (!res.ok) return;
    const devices = await res.json();
    const select = document.getElementById("deviceSelect");
    select.innerHTML = "";
    devices.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d.id;
      opt.textContent = `${d.device_name} (${d.id})`;
      select.appendChild(opt);
    });
    if (devices.length > 0) {
      activeDeviceId = devices[0].id;
    }
  } catch (err) {
    console.error("Failed to load devices", err);
  }
}

async function fetchLatestState() {
  try {
    const res = await fetch(`/api/v1/devices/${activeDeviceId}/latest`);
    if (!res.ok) return;
    const data = await res.json();
    updateDashboardUI(data);
  } catch (err) {
    console.error("Error fetching latest state", err);
  }
}

function updateDashboardUI(data) {
  const device = data.device;
  const telemetry = data.latest_telemetry;

  // Liveness & Heartbeat
  const connBadge = document.getElementById("connectionBadge");
  const connText = document.getElementById("connectionText");
  const lastSeenText = document.getElementById("lastSeenText");

  if (device.status === "ONLINE") {
    connBadge.className = "flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-emerald-950/60 border border-emerald-800 text-emerald-400 text-xs font-semibold";
    connText.innerText = "ONLINE";
  } else {
    connBadge.className = "flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-red-950/60 border border-red-800 text-red-400 text-xs font-semibold";
    connText.innerText = "OFFLINE";
  }

  if (device.last_seen) {
    const d = new Date(device.last_seen);
    lastSeenText.innerText = d.toLocaleTimeString();
  }

  // Botanical threshold indicators
  document.getElementById("labelMinThresh").innerText = device.moisture_threshold_min;
  document.getElementById("labelMaxThresh").innerText = device.moisture_threshold_max;

  // Health Score Badge
  const healthBadge = document.getElementById("healthScoreBadge");
  healthBadge.innerText = `HEALTH: ${device.health_score}%`;
  if (device.health_score > 80) {
    healthBadge.className = "text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-emerald-950 text-emerald-400 border border-emerald-800";
  } else if (device.health_score > 50) {
    healthBadge.className = "text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-amber-950 text-amber-400 border border-amber-800";
  } else {
    healthBadge.className = "text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-red-950 text-red-400 border border-red-800";
  }

  // Telemetry Cards
  if (telemetry) {
    // Moisture
    const m = telemetry.soil_moisture;
    document.getElementById("metricMoisture").innerText = m.toFixed(1);
    document.getElementById("moistureBar").style.width = `${Math.min(100, Math.max(0, m))}%`;

    const mBadge = document.getElementById("moistureBadge");
    if (m < device.moisture_threshold_min) {
      mBadge.innerText = "DRY (DEFICIT)";
      mBadge.className = "text-[10px] px-2 py-0.5 rounded-full bg-red-500/20 text-red-300 border border-red-500/30";
    } else if (m > device.moisture_threshold_max) {
      mBadge.innerText = "SATURATED";
      mBadge.className = "text-[10px] px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30";
    } else {
      mBadge.innerText = "OPTIMAL";
      mBadge.className = "text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30";
    }

    // Temperature
    const t = telemetry.temperature;
    document.getElementById("metricTemp").innerText = t.toFixed(1);
    document.getElementById("tempIcon").innerText = t > 30 ? "🔥" : (t < 18 ? "❄️" : "🌡️");
    document.getElementById("tempStatus").innerText = t > 35 ? "High heat alert" : "Normal thermal range";

    // Humidity
    const h = telemetry.humidity;
    document.getElementById("metricHumidity").innerText = h.toFixed(1);
    document.getElementById("humidityBar").style.width = `${Math.min(100, Math.max(0, h))}%`;

    // Light
    const lux = telemetry.light_level;
    document.getElementById("metricLight").innerText = Math.round(lux);
    document.getElementById("sunIcon").innerText = lux > 1000 ? "☀️" : "🌙";
    document.getElementById("lightDescription").innerText = lux > 20000 ? "High sunlight" : (lux > 1000 ? "Moderate light" : "Darkness / night");

    // Tank Level
    const tank = telemetry.water_tank_level;
    document.getElementById("metricTank").innerText = tank.toFixed(1);
    document.getElementById("tankBar").style.width = `${Math.min(100, Math.max(0, tank))}%`;

    const tankBadge = document.getElementById("tankBadge");
    if (tank < 10) {
      tankBadge.innerText = "DEPLETED";
      tankBadge.className = "text-[10px] px-2 py-0.5 rounded-full bg-red-500/20 text-red-300 border border-red-500/30";
    } else if (tank < 25) {
      tankBadge.innerText = "LOW";
      tankBadge.className = "text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30";
    } else {
      tankBadge.innerText = "ADEQUATE";
      tankBadge.className = "text-[10px] px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30";
    }
  }

  // Virtual Pump Actuator Widget
  const pumpWidgetBox = document.getElementById("pumpWidgetBox");
  const pumpTitle = document.getElementById("pumpStatusTitle");
  const pumpSub = document.getElementById("pumpStatusSubtitle");
  const pumpIcon = document.getElementById("pumpIcon");
  const btnActuate = document.getElementById("btnManualActuate");
  const cooldownBox = document.getElementById("cooldownBox");

  if (device.active_pump) {
    pumpWidgetBox.className = "rounded-xl border border-cyan-500/60 bg-cyan-950/40 p-5 text-center transition-all duration-300 glow-active";
    pumpTitle.innerText = "VIRTUAL PUMP: ACTIVE (WATERING)";
    pumpTitle.className = "text-base font-bold text-cyan-300 tracking-wide water-anim";
    pumpSub.innerText = "Irrigation pulse running on physical actuator";
    pumpIcon.className = "w-8 h-8 text-cyan-400";
    btnActuate.disabled = true;
  } else {
    pumpWidgetBox.className = "rounded-xl border border-slate-800 bg-slate-950/60 p-5 text-center transition-all duration-300";
    pumpTitle.innerText = "VIRTUAL PUMP: IDLE";
    pumpTitle.className = "text-base font-bold text-white tracking-wide";
    pumpSub.innerText = "Standing by for hysteresis trigger";
    pumpIcon.className = "w-8 h-8 text-slate-400";

    // Handle Cooldown
    if (device.cooldown_remaining_seconds > 0) {
      cooldownBox.classList.remove("hidden");
      document.getElementById("cooldownCountdownTimer").innerText = `${device.cooldown_remaining_seconds}s`;
      btnActuate.disabled = true;
      document.getElementById("btnManualActuateText").innerText = `Cooldown Lockout (${device.cooldown_remaining_seconds}s)`;
    } else {
      cooldownBox.classList.add("hidden");
      btnActuate.disabled = false;
      document.getElementById("btnManualActuateText").innerText = "Manual Irrigation Pulse (5s)";
    }
  }
}

async function fetchHistory() {
  try {
    const res = await fetch(`/api/v1/devices/${activeDeviceId}/history?hours=12`);
    if (!res.ok) return;
    const data = await res.json();

    const readings = data.readings || [];
    document.getElementById("datapointsCount").innerText = `${readings.length} records synced`;

    const labels = readings.map((r) => {
      const d = new Date(r.created_at);
      return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
    });

    const moistureData = readings.map((r) => r.soil_moisture);
    const tempData = readings.map((r) => r.temperature);

    telemetryChart.data.labels = labels;
    telemetryChart.data.datasets[0].data = moistureData;
    telemetryChart.data.datasets[1].data = tempData;
    telemetryChart.update("none");
  } catch (err) {
    console.error("Error fetching history", err);
  }
}

let topAlarmId = null;

async function fetchAlerts() {
  try {
    const res = await fetch("/api/v1/alerts?unack_only=true&limit=20");
    if (!res.ok) return;
    const alerts = await res.json();

    const badge = document.getElementById("activeAlarmsBadge");
    badge.innerText = `${alerts.length} active`;
    badge.className = alerts.length > 0
      ? "text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 border border-red-500/30"
      : "text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400";

    // Alarm banner
    const banner = document.getElementById("alarmBanner");
    const critical = alerts.find((a) => a.severity === "CRITICAL");
    if (critical) {
      topAlarmId = critical.id;
      document.getElementById("alarmBannerTitle").innerText = `CRITICAL ALARM: ${critical.alert_type}`;
      document.getElementById("alarmBannerMessage").innerText = critical.message;
      banner.classList.remove("hidden");
    } else {
      topAlarmId = null;
      banner.classList.add("hidden");
    }

    // Alerts Table
    const tbody = document.getElementById("alertsTableBody");
    tbody.innerHTML = "";

    if (alerts.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="py-6 text-center text-slate-500">No active operational alarms reported. System stable.</td></tr>`;
      return;
    }

    alerts.forEach((alert) => {
      const tr = document.createElement("tr");
      const d = new Date(alert.created_at);
      const timeStr = `${d.toLocaleDateString()} ${d.toLocaleTimeString()}`;

      let severityClass = "bg-blue-500/20 text-blue-300 border-blue-500/30";
      if (alert.severity === "CRITICAL") severityClass = "bg-red-500/20 text-red-300 border-red-500/30";
      if (alert.severity === "WARNING") severityClass = "bg-amber-500/20 text-amber-300 border-amber-500/30";

      tr.innerHTML = `
        <td class="py-2.5 px-3 font-mono text-slate-400">${timeStr}</td>
        <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded border text-[10px] font-semibold ${severityClass}">${alert.severity}</span></td>
        <td class="py-2.5 px-3 font-semibold text-slate-200">${alert.alert_type}</td>
        <td class="py-2.5 px-3 text-slate-300">${alert.message}</td>
        <td class="py-2.5 px-3 text-right">
          <button onclick="ackAlert('${alert.id}')" class="px-2 py-1 text-[11px] rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">
            Acknowledge
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });

  } catch (err) {
    console.error("Error fetching alerts", err);
  }
}

async function ackTopAlarm() {
  if (topAlarmId) {
    await ackAlert(topAlarmId);
  }
}

async function ackAlert(alertId) {
  try {
    const res = await fetch(`/api/v1/alerts/${alertId}/ack`, { method: "PUT" });
    if (res.ok) {
      fetchAlerts();
    }
  } catch (err) {
    console.error("Failed to acknowledge alert", err);
  }
}

async function triggerManualIrrigation() {
  const btn = document.getElementById("btnManualActuate");
  btn.disabled = true;
  document.getElementById("btnManualActuateText").innerText = "Actuating Pump...";

  try {
    const res = await fetch(`/api/v1/devices/${activeDeviceId}/actuate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ duration_seconds: 5.0, reason: "Manual operator pulse from Web Dashboard" })
    });

    const data = await res.json();
    if (res.ok) {
      fetchLatestState();
      fetchHistory();
    } else {
      alert(`Actuation Rejected: ${data.detail || "Cooldown active or server rejected request"}`);
      fetchLatestState();
    }
  } catch (err) {
    console.error("Failed to actuate irrigation", err);
    alert("Network error communicating with backend.");
  }
}

async function saveDeviceConfig() {
  const species = document.getElementById("speciesProfileSelect").value;
  const minM = parseFloat(document.getElementById("sliderMinMoisture").value);
  const maxM = parseFloat(document.getElementById("sliderMaxMoisture").value);

  try {
    const res = await fetch(`/api/v1/devices/${activeDeviceId}/config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plant_species: species,
        moisture_threshold_min: minM,
        moisture_threshold_max: maxM
      })
    });

    if (res.ok) {
      alert(`Configuration successfully updated for node ${activeDeviceId}!`);
      fetchLatestState();
    } else {
      const err = await res.json();
      alert(`Failed to update configuration: ${err.detail}`);
    }
  } catch (e) {
    console.error("Error saving config", e);
  }
}
