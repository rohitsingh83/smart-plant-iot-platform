/**
 * Apex Smart Plant Care & Digital Twin Platform
 * Full Autonomous In-Browser Cyber-Physical Engine & Live Cloud Gateway
 * Features:
 * - Fluid SVG Botanical Plant Reactions (wilting, thriving, watering perk-up)
 * - Animated Water Sprinklers, Droplets & Hydraulic Pipe Flow
 * - 24-Hour Sinusoidal Diurnal Solar Cycles (Sun/Moon Horizon)
 * - In-Browser Physics Engine with Hysteresis & Anti-Flapping Cooldown
 * - Seamless Cloud REST API sync when connected to Render or local backend
 */

// ==============================================================
// 1. STATE VARIABLES & CONFIGURATION
// ==============================================================
let activeMode = "autonomous"; // "autonomous" or "cloud"
let activeDeviceId = "esp32-greenhouse-01";
let telemetryChart = null;

// Botanical Presets
const BOTANICAL_PRESETS = {
  "Tropical Foliage": { min: 45, max: 75, pump: 5, cooldown: 25, speciesName: "Tropical Foliage" },
  "Succulents": { min: 20, max: 35, pump: 4, cooldown: 60, speciesName: "Succulents & Cacti" },
  "Vegetables/Tomatoes": { min: 40, max: 65, pump: 6, cooldown: 35, speciesName: "Tomatoes" },
  "Culinary Herbs": { min: 35, max: 55, pump: 5, cooldown: 30, speciesName: "Culinary Herbs" }
};

let currentConfig = {
  plantSpecies: "Tropical Foliage",
  minMoisture: 45.0,
  maxMoisture: 75.0,
  pumpDuration: 5.0,
  cooldownMinutes: 25.0
};

// Autonomous Cyber-Physical State Twin
const physicsTwin = {
  soilMoisture: 58.0,
  temperature: 23.5,
  humidity: 62.0,
  lightLevel: 4500.0,
  waterTankLevel: 94.0,
  pumpActive: false,
  pumpRemainingSec: 0.0,
  cooldownRemainingSec: 0,
  simTimeSec: 10.5 * 3600, // Starts at 10:30 AM
  lastWateringTime: 0,
  alerts: []
};

// Historical Data Buffer for Chart.js
const historyBuffer = {
  labels: [],
  moisture: [],
  temperature: []
};

// Cloud API Configuration
let apiBaseUrl = localStorage.getItem("PLANT_CARE_API_URL") || "";

function getApiUrl(endpoint) {
  if (!apiBaseUrl) return endpoint;
  return `${apiBaseUrl.replace(/\/$/, '')}${endpoint}`;
}

async function cloudFetch(endpoint, options = {}) {
  const url = getApiUrl(endpoint);
  options.headers = {
    ...(options.headers || {}),
    "Bypass-Tunnel-Reminder": "true"
  };
  return fetch(url, options);
}

// ==============================================================
// 2. INITIALIZATION
// ==============================================================
document.addEventListener("DOMContentLoaded", () => {
  initChart();
  setupEventListeners();
  seedInitialHistory();
  updateUI();

  // Run autonomous continuous physics engine at 1 Hz (1 sec real-time)
  setInterval(tickSimulationEngine, 1000);
});

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
          backgroundColor: "rgba(16, 185, 129, 0.12)",
          fill: true,
          tension: 0.35,
          yAxisID: "yMoisture",
          borderWidth: 2.5,
          pointRadius: 2,
          pointHoverRadius: 5
        },
        {
          label: "Temperature (°C)",
          data: [],
          borderColor: "#f59e0b",
          backgroundColor: "transparent",
          tension: 0.35,
          yAxisID: "yTemp",
          borderWidth: 2,
          pointRadius: 1.5,
          pointHoverRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400 },
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { color: "rgba(51, 65, 85, 0.4)" },
          ticks: { color: "#94a3b8", maxTicksLimit: 7, font: { size: 10 } }
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
          max: 42,
          grid: { drawOnChartArea: false },
          ticks: { color: "#f59e0b", font: { size: 10 } }
        }
      }
    }
  });
}

function seedInitialHistory() {
  const now = new Date();
  for (let i = 18; i >= 0; i--) {
    const t = new Date(now.getTime() - i * 15000);
    const timeStr = `${t.getHours().toString().padStart(2, '0')}:${t.getMinutes().toString().padStart(2, '0')}:${t.getSeconds().toString().padStart(2, '0')}`;
    historyBuffer.labels.push(timeStr);
    historyBuffer.moisture.push(Number((60.0 - i * 0.25 + Math.sin(i)).toFixed(1)));
    historyBuffer.temperature.push(Number((23.0 + Math.sin(i * 0.5) * 1.5).toFixed(1)));
  }
  syncChartData();
}

function syncChartData() {
  if (!telemetryChart) return;
  telemetryChart.data.labels = [...historyBuffer.labels];
  telemetryChart.data.datasets[0].data = [...historyBuffer.moisture];
  telemetryChart.data.datasets[1].data = [...historyBuffer.temperature];
  telemetryChart.update("none");
}

// ==============================================================
// 3. AUTONOMOUS CONTINUOUS CYBER-PHYSICAL ENGINE
// ==============================================================
function tickSimulationEngine() {
  if (activeMode === "cloud") {
    fetchCloudTelemetry();
    return;
  }

  // Advance simulated clock (1 real second = 45 simulated seconds)
  const dt = 45.0;
  physicsTwin.simTimeSec = (physicsTwin.simTimeSec + dt) % 86400;

  // 1. Diurnal Sun/Temp Cycles
  const solarPhase = (physicsTwin.simTimeSec / 86400) * 2.0 * Math.PI;
  const sunElevation = Math.sin(solarPhase - Math.PI / 2.0); // +1 at noon, -1 at midnight

  if (sunElevation > 0) {
    physicsTwin.lightLevel = Math.max(100, Math.round(sunElevation * 58000 + (Math.random() * 200 - 100)));
  } else {
    physicsTwin.lightLevel = Math.max(10, Math.round(20 + Math.random() * 10));
  }

  // Temperature lags sun peak by ~2 hours
  const tempWave = Math.sin(solarPhase - Math.PI / 2.0 - 0.5);
  physicsTwin.temperature = Number((21.5 + 8.0 * tempWave + (Math.random() * 0.2 - 0.1)).toFixed(1));

  // Humidity inversely correlated with temperature
  const normTemp = (physicsTwin.temperature - 13.0) / 20.0;
  physicsTwin.humidity = Math.max(20, Math.min(95, Number((84.0 - normTemp * 42.0).toFixed(1))));

  // 2. Cooldown timer countdown
  if (physicsTwin.cooldownRemainingSec > 0) {
    physicsTwin.cooldownRemainingSec--;
  }

  // 3. Hydrological Absorption vs. Natural Desiccation
  if (physicsTwin.pumpActive && physicsTwin.pumpRemainingSec > 0) {
    // Active watering: Soil absorbs water rapidly
    physicsTwin.soilMoisture = Math.min(currentConfig.maxMoisture + 8.0, physicsTwin.soilMoisture + 4.8);
    physicsTwin.waterTankLevel = Math.max(0, physicsTwin.waterTankLevel - 0.8);
    physicsTwin.pumpRemainingSec -= 1.0;

    if (physicsTwin.pumpRemainingSec <= 0) {
      physicsTwin.pumpActive = false;
      physicsTwin.cooldownRemainingSec = Math.round(currentConfig.cooldownMinutes * 60);
      physicsTwin.alerts.unshift({
        id: "ev-" + Date.now(),
        severity: "INFO",
        alert_type: "WATERING_PULSE_COMPLETED",
        message: `Irrigation pulse complete. Hydrated to ${physicsTwin.soilMoisture.toFixed(1)}%. Cooldown active.`,
        created_at: new Date().toISOString()
      });
    }
  } else {
    physicsTwin.pumpActive = false;

    // Natural exponential drying equation:
    // dM = k * (T / 24) * (1 + Light / 12000) * dt
    const thermalFactor = Math.max(0.6, physicsTwin.temperature / 24.0);
    const lightFactor = 1.0 + physicsTwin.lightLevel / 12000.0;
    const evaporationDelta = 0.00075 * thermalFactor * lightFactor * dt;
    physicsTwin.soilMoisture = Math.max(8.0, Number((physicsTwin.soilMoisture - evaporationDelta).toFixed(2)));

    // 4. Automated Dual-Threshold Hysteresis Evaluation
    if (physicsTwin.soilMoisture <= currentConfig.minMoisture) {
      // Check tank cavitation guardrail
      if (physicsTwin.waterTankLevel < 10.0) {
        if (!physicsTwin.alerts.find(a => a.alert_type === "TANK_EMPTY")) {
          physicsTwin.alerts.unshift({
            id: "al-" + Date.now(),
            severity: "CRITICAL",
            alert_type: "TANK_EMPTY",
            message: "Reservoir depleted (<10%). Pump locked out to prevent cavitation.",
            created_at: new Date().toISOString()
          });
        }
      } else if (physicsTwin.cooldownRemainingSec <= 0) {
        // Trigger automated pulse!
        triggerActuation(currentConfig.pumpDuration, "AUTOMATIC_HYSTERESIS");
      }
    }
  }

  // 5. Append to Chart.js stream
  const now = new Date();
  const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
  historyBuffer.labels.push(timeStr);
  historyBuffer.moisture.push(physicsTwin.soilMoisture);
  historyBuffer.temperature.push(physicsTwin.temperature);

  if (historyBuffer.labels.length > 25) {
    historyBuffer.labels.shift();
    historyBuffer.moisture.shift();
    historyBuffer.temperature.shift();
  }
  syncChartData();

  // 6. Update Visual UI & Animations
  updateUI();
}

function triggerActuation(durationSec, triggerType) {
  if (physicsTwin.cooldownRemainingSec > 0) return;

  physicsTwin.pumpActive = true;
  physicsTwin.pumpRemainingSec = durationSec;
  physicsTwin.lastWateringTime = Date.now();

  physicsTwin.alerts.unshift({
    id: "act-" + Date.now(),
    severity: "INFO",
    alert_type: triggerType,
    message: `Pump engaged for ${durationSec.toFixed(1)}s (${triggerType}).`,
    created_at: new Date().toISOString()
  });
}

// ==============================================================
// 4. VISUAL RENDERING & BOTANICAL ANIMATIONS
// ==============================================================
function updateUI() {
  const m = physicsTwin.soilMoisture;
  const t = physicsTwin.temperature;
  const h = physicsTwin.humidity;
  const lux = physicsTwin.lightLevel;
  const tank = physicsTwin.waterTankLevel;

  // 1. KPI Numbers & Progress Bars
  document.getElementById("metricMoisture").innerText = m.toFixed(1);
  document.getElementById("moistureBar").style.width = `${Math.min(100, Math.max(0, m))}%`;

  document.getElementById("metricTemp").innerText = t.toFixed(1);
  document.getElementById("tempIcon").innerText = t > 30 ? "🔥" : (t < 18 ? "❄️" : "🌡️");
  document.getElementById("tempStatus").innerText = t > 35 ? "High heat spike" : "Optimal thermal range";

  document.getElementById("metricHumidity").innerText = h.toFixed(1);
  document.getElementById("humidityBar").style.width = `${Math.min(100, Math.max(0, h))}%`;

  document.getElementById("metricLight").innerText = Math.round(lux);
  document.getElementById("sunIcon").innerText = lux > 800 ? "☀️" : "🌙";
  document.getElementById("lightDescription").innerText = lux > 20000 ? "Direct sunlight" : (lux > 800 ? "Diffused daylight" : "Night darkness");

  document.getElementById("metricTank").innerText = tank.toFixed(1);
  document.getElementById("tankBar").style.width = `${Math.min(100, Math.max(0, tank))}%`;

  // 2. Moisture Badge
  const mBadge = document.getElementById("moistureBadge");
  if (m < currentConfig.minMoisture) {
    mBadge.innerText = "DEFICIT (DRY)";
    mBadge.className = "text-[10px] px-2 py-0.5 rounded-full bg-red-500/20 text-red-300 border border-red-500/30";
  } else if (m > currentConfig.maxMoisture) {
    mBadge.innerText = "SATURATED";
    mBadge.className = "text-[10px] px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30";
  } else {
    mBadge.innerText = "OPTIMAL";
    mBadge.className = "text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30";
  }

  // 3. Tank Badge
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

  // 4. Botanical Plant Avatar & Visual Physics Animations
  const plantGroup = document.getElementById("plantGroup");
  const soilEllipse = document.getElementById("soilEllipse");
  const plantMoodBadge = document.getElementById("plantMoodBadge");
  const waterDroplets = document.getElementById("waterDroplets");
  const waterRipple = document.getElementById("waterRipple");

  // Health Score Calculation
  let health = 100.0;
  if (m < currentConfig.minMoisture) health -= (currentConfig.minMoisture - m) * 2.2;
  if (t > 34) health -= (t - 34) * 5.0;
  if (tank < 15) health -= 20.0;
  health = Math.max(0, Math.min(100, Math.round(health)));

  document.getElementById("heroHealthText").innerText = `${health}.0%`;
  document.getElementById("heroHealthRing").innerText = health;

  if (m < 28) {
    // Desiccated / Wilting Plant
    plantGroup.style.transform = "scaleY(0.78) rotate(4deg)";
    soilEllipse.setAttribute("fill", "#6b4a2e"); // Pale dry dirt
    plantMoodBadge.innerText = "🥀 Desiccated (Watering Required)";
    plantMoodBadge.className = "mt-2 text-xs font-semibold px-3 py-1 rounded-full bg-red-500/20 text-red-300 border border-red-500/40";
  } else if (physicsTwin.pumpActive) {
    // Actively Watering: Bouncing perk-up & lush
    plantGroup.style.transform = "scaleY(1.04) rotate(-0.5deg)";
    soilEllipse.setAttribute("fill", "#1c1108"); // Dark rich wet soil
    plantMoodBadge.innerText = "💧 Hydrating & Absorbing";
    plantMoodBadge.className = "mt-2 text-xs font-semibold px-3 py-1 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 animate-pulse";
  } else {
    // Healthy & Thriving
    plantGroup.style.transform = "scaleY(1.0) rotate(0deg)";
    soilEllipse.setAttribute("fill", "#2d1e12");
    plantMoodBadge.innerText = "🌱 Thriving & Hydrated";
    plantMoodBadge.className = "mt-2 text-xs font-semibold px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
  }

  // 5. Actuator State Machine & Hydraulic Pipe Animations
  const pumpBox = document.getElementById("pumpWidgetBox");
  const pumpTitle = document.getElementById("pumpStatusTitle");
  const pumpSub = document.getElementById("pumpStatusSubtitle");
  const pumpImpeller = document.getElementById("pumpImpellerIcon");
  const pumpCountdownBox = document.getElementById("pumpCountdownBox");
  const cooldownBox = document.getElementById("cooldownBox");
  const btnActuate = document.getElementById("btnManualActuate");
  const pipeWaterFlow = document.getElementById("pipeWaterFlow");
  const pipeFlowText = document.getElementById("pipeFlowText");

  if (physicsTwin.pumpActive) {
    // Pumping
    pumpBox.className = "mt-2 rounded-xl border border-cyan-500 bg-cyan-950/50 p-4 text-center transition-all duration-300 glow-active";
    pumpTitle.innerText = "VIRTUAL PUMP: ACTIVE (WATERING)";
    pumpTitle.className = "text-sm font-bold text-cyan-300 tracking-wide water-pulse";
    pumpSub.innerText = "Irrigation solenoid energized";
    pumpImpeller.classList.add("spin-fast");
    pumpImpeller.classList.remove("text-slate-400");
    pumpImpeller.classList.add("text-cyan-400");

    // Hydraulic Flow
    pipeWaterFlow.classList.remove("hidden");
    pipeFlowText.innerText = "FLOWING";
    pipeFlowText.className = "text-[10px] font-mono text-cyan-400 font-bold";

    // Water Spray Nozzle Droplets
    waterDroplets.classList.remove("hidden");
    waterRipple.classList.remove("hidden");

    pumpCountdownBox.classList.remove("hidden");
    document.getElementById("pumpCountdownTimer").innerText = `${physicsTwin.pumpRemainingSec.toFixed(1)}s`;
    btnActuate.disabled = true;
  } else {
    // Idle
    pumpBox.className = "mt-2 rounded-xl border border-slate-800 bg-slate-900/70 p-4 text-center transition-all duration-300";
    pumpTitle.innerText = "VIRTUAL PUMP: IDLE";
    pumpTitle.className = "text-sm font-bold text-white tracking-wide";
    pumpSub.innerText = "Standing by for hysteresis trigger";
    pumpImpeller.classList.remove("spin-fast");
    pumpImpeller.classList.remove("text-cyan-400");
    pumpImpeller.classList.add("text-slate-400");

    pipeWaterFlow.classList.add("hidden");
    pipeFlowText.innerText = "CLOSED";
    pipeFlowText.className = "text-[10px] font-mono text-slate-500";

    waterDroplets.classList.add("hidden");
    waterRipple.classList.add("hidden");
    pumpCountdownBox.classList.add("hidden");

    // Cooldown Lockout Check
    if (physicsTwin.cooldownRemainingSec > 0) {
      cooldownBox.classList.remove("hidden");
      document.getElementById("cooldownCountdownTimer").innerText = `${physicsTwin.cooldownRemainingSec}s`;
      btnActuate.disabled = true;
      document.getElementById("btnManualActuateText").innerText = `Cooldown Lockout (${physicsTwin.cooldownRemainingSec}s)`;
    } else {
      cooldownBox.classList.add("hidden");
      btnActuate.disabled = false;
      document.getElementById("btnManualActuateText").innerText = "Manual Irrigation Pulse (5s)";
    }
  }

  // 6. Day / Night Horizon Sky Display
  const simHours = Math.floor(physicsTwin.simTimeSec / 3600);
  const simMins = Math.floor((physicsTwin.simTimeSec % 3600) / 60);
  const ampm = simHours >= 12 ? "PM" : "AM";
  const displayHours = simHours % 12 || 12;
  document.getElementById("skyTimeText").innerText = `${displayHours}:${simMins.toString().padStart(2, '0')} ${ampm}`;
  document.getElementById("skyIcon").innerText = (simHours >= 6 && simHours < 19) ? "☀️" : "🌙";

  // 7. Render Alarms Table
  renderAlerts();
}

function renderAlerts() {
  const tbody = document.getElementById("alertsTableBody");
  const badge = document.getElementById("activeAlarmsBadge");
  const alerts = physicsTwin.alerts.slice(0, 15);

  badge.innerText = `${alerts.length} active`;

  if (alerts.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="py-6 text-center text-slate-500">No active operational alarms reported. System stable.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  alerts.forEach(alert => {
    const tr = document.createElement("tr");
    const d = new Date(alert.created_at);
    const timeStr = `${d.toLocaleDateString()} ${d.toLocaleTimeString()}`;

    let sevClass = "bg-blue-500/20 text-blue-300 border-blue-500/30";
    if (alert.severity === "CRITICAL") sevClass = "bg-red-500/20 text-red-300 border-red-500/30";
    if (alert.severity === "WARNING") sevClass = "bg-amber-500/20 text-amber-300 border-amber-500/30";

    tr.innerHTML = `
      <td class="py-2.5 px-3 font-mono text-slate-400">${timeStr}</td>
      <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded border text-[10px] font-semibold ${sevClass}">${alert.severity}</span></td>
      <td class="py-2.5 px-3 font-semibold text-slate-200">${alert.alert_type}</td>
      <td class="py-2.5 px-3 text-slate-300">${alert.message}</td>
      <td class="py-2.5 px-3 text-right">
        <button onclick="dismissAlert('${alert.id}')" class="px-2 py-1 text-[11px] rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">
          Acknowledge
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

window.dismissAlert = function(id) {
  physicsTwin.alerts = physicsTwin.alerts.filter(a => a.id !== id);
  renderAlerts();
};

// ==============================================================
// 5. EVENT LISTENERS & OPERATING MODES
// ==============================================================
function setupEventListeners() {
  // Mode Buttons
  const btnModeSim = document.getElementById("btnModeSim");
  const btnModeCloud = document.getElementById("btnModeCloud");

  btnModeSim.addEventListener("click", () => {
    activeMode = "autonomous";
    btnModeSim.className = "px-2.5 py-1 rounded-md text-[11px] font-semibold bg-emerald-600 text-white transition";
    btnModeCloud.className = "px-2.5 py-1 rounded-md text-[11px] font-medium text-slate-400 hover:text-white transition";
    document.getElementById("syncModeIndicator").innerText = "Continuous Real-Time Simulation Engine Active";
    document.getElementById("connectionText").innerText = "ONLINE";
  });

  btnModeCloud.addEventListener("click", () => {
    activeMode = "cloud";
    btnModeCloud.className = "px-2.5 py-1 rounded-md text-[11px] font-semibold bg-cyan-600 text-white transition";
    btnModeSim.className = "px-2.5 py-1 rounded-md text-[11px] font-medium text-slate-400 hover:text-white transition";
    document.getElementById("syncModeIndicator").innerText = "Cloud Gateway REST Polling Active";
    fetchCloudTelemetry();
  });

  // Manual Trigger Button
  document.getElementById("btnManualActuate").addEventListener("click", () => {
    if (activeMode === "autonomous") {
      triggerActuation(currentConfig.pumpDuration, "MANUAL_OVERRIDE");
    } else {
      triggerCloudActuation();
    }
  });

  // Species Profile Presets
  const speciesSelect = document.getElementById("speciesProfileSelect");
  speciesSelect.addEventListener("change", (e) => {
    const profile = BOTANICAL_PRESETS[e.target.value];
    if (profile) {
      currentConfig.plantSpecies = e.target.value;
      currentConfig.minMoisture = profile.min;
      currentConfig.maxMoisture = profile.max;
      currentConfig.pumpDuration = profile.pump;
      currentConfig.cooldownMinutes = profile.cooldown;

      document.getElementById("sliderMinMoisture").value = profile.min;
      document.getElementById("sliderMinVal").innerText = `${profile.min}%`;
      document.getElementById("sliderMaxMoisture").value = profile.max;
      document.getElementById("sliderMaxVal").innerText = `${profile.max}%`;
      document.getElementById("plantStageSpeciesBadge").innerText = profile.speciesName;
      document.getElementById("labelMinThresh").innerText = profile.min;
      document.getElementById("labelMaxThresh").innerText = profile.max;
    }
  });

  // Sliders
  document.getElementById("sliderMinMoisture").addEventListener("input", (e) => {
    currentConfig.minMoisture = parseFloat(e.target.value);
    document.getElementById("sliderMinVal").innerText = `${e.target.value}%`;
    document.getElementById("labelMinThresh").innerText = e.target.value;
  });

  document.getElementById("sliderMaxMoisture").addEventListener("input", (e) => {
    currentConfig.maxMoisture = parseFloat(e.target.value);
    document.getElementById("sliderMaxVal").innerText = `${e.target.value}%`;
    document.getElementById("labelMaxThresh").innerText = e.target.value;
  });

  document.getElementById("btnSaveConfig").addEventListener("click", () => {
    alert(`Configuration applied: ${currentConfig.plantSpecies} [Min: ${currentConfig.minMoisture}%, Saturation: ${currentConfig.maxMoisture}%]`);
  });

  // Cloud URL Config Modal
  document.getElementById("btnConfigureCloudUrl").addEventListener("click", () => {
    const current = apiBaseUrl || "";
    const entered = prompt("Enter Cloud Gateway Backend URL (e.g. https://smart-plant-backend.onrender.com or leave blank for Autonomous mode):", current);
    if (entered !== null) {
      apiBaseUrl = entered.trim().replace(/\/$/, "");
      localStorage.setItem("PLANT_CARE_API_URL", apiBaseUrl);
      document.getElementById("cloudUrlDisplay").innerText = apiBaseUrl ? "Cloud API" : "Autonomous";
    }
  });

  document.getElementById("btnRefreshAlerts").addEventListener("click", () => {
    renderAlerts();
  });
}

// ==============================================================
// 6. CLOUD GATEWAY REST SYNC (OPTIONAL WHEN CONNECTED)
// ==============================================================
async function fetchCloudTelemetry() {
  try {
    const res = await cloudFetch(`/api/v1/devices/${activeDeviceId}/latest`);
    if (!res.ok) throw new Error("Cloud unreachable");
    const data = await res.json();

    if (data.latest_telemetry) {
      physicsTwin.soilMoisture = data.latest_telemetry.soil_moisture;
      physicsTwin.temperature = data.latest_telemetry.temperature;
      physicsTwin.humidity = data.latest_telemetry.humidity;
      physicsTwin.lightLevel = data.latest_telemetry.light_level;
      physicsTwin.waterTankLevel = data.latest_telemetry.water_tank_level;
    }
    if (data.device) {
      physicsTwin.pumpActive = data.device.active_pump;
      physicsTwin.cooldownRemainingSec = data.device.cooldown_remaining_seconds;
    }

    document.getElementById("connectionText").innerText = "ONLINE (CLOUD)";
    updateUI();
  } catch (err) {
    console.warn("Cloud gateway offline, running autonomous twin", err);
    document.getElementById("connectionText").innerText = "AUTONOMOUS";
    activeMode = "autonomous";
  }
}

async function triggerCloudActuation() {
  try {
    const res = await cloudFetch(`/api/v1/devices/${activeDeviceId}/actuate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ duration_seconds: 5.0, reason: "Manual pulse from web dashboard" })
    });
    if (res.ok) {
      fetchCloudTelemetry();
    } else {
      const err = await res.json();
      alert(`Cloud Actuation Rejected: ${err.detail}`);
    }
  } catch (e) {
    // Fallback to local
    triggerActuation(5.0, "MANUAL_OVERRIDE");
  }
}
