document.addEventListener("DOMContentLoaded", () => {
  initTelemetryGauges();
  initActionButtons();
  initInteractiveChart();
  initHealSimulation();
  initRemediationHistoryEvents();
  
  // New sub-dashboard interactivity initializers
  initLogsSearchAndFilter();
  initAlertsSearchAndFilter();
  initKubernetesActions();
  initPredictionActions();
  initDeploymentsActions();
  initPipelineActions();
  initSettingsActions();
  
  // Global button & interactive element handlers
  initGlobalButtonActions();
});

// Helper to update mini SVG circular loaders
function updateCircleProgress(element, percent) {
  if (element) {
    element.setAttribute("stroke-dasharray", `${percent}, 100`);
  }
}

// 1. Oscillating Telemetry Gauges to make UI feel alive
let currentCpu = 65;
let currentMemory = 58;

function initTelemetryGauges() {
  const cpuPercentText = document.getElementById("cpu-percent");
  const memoryPercentText = document.getElementById("memory-percent");
  const cpuCircle = document.getElementById("cpu-circle");
  const memoryCircle = document.getElementById("memory-circle");

  // Initial values
  if (cpuPercentText) cpuPercentText.textContent = `${currentCpu}%`;
  updateCircleProgress(cpuCircle, currentCpu);

  if (memoryPercentText) memoryPercentText.textContent = `${currentMemory}%`;
  updateCircleProgress(memoryCircle, currentMemory);

  // Soft oscillation loop
  setInterval(() => {
    // Oscillate CPU (55% to 75%)
    const cpuDelta = Math.floor(Math.random() * 5) - 2; // -2 to +2
    currentCpu = Math.max(55, Math.min(75, currentCpu + cpuDelta));
    if (cpuPercentText) cpuPercentText.textContent = `${currentCpu}%`;
    updateCircleProgress(cpuCircle, currentCpu);

    // Oscillate Memory (52% to 62%)
    const memDelta = Math.floor(Math.random() * 3) - 1; // -1 to +1
    currentMemory = Math.max(50, Math.min(65, currentMemory + memDelta));
    if (memoryPercentText) memoryPercentText.textContent = `${currentMemory}%`;
    updateCircleProgress(memoryCircle, currentMemory);
  }, 4000);
}

// 2. Action Deck Button Interactions
function initActionButtons() {
  const viewLogsBtn = document.getElementById("btn-view-logs");
  const rollbackBtn = document.getElementById("btn-rollback");
  const systemCheckBtn = document.getElementById("btn-system-check");

  if (viewLogsBtn) {
    viewLogsBtn.addEventListener("click", () => {
      showFlashNotification("Opening deployment logs...", "var(--purple-gauge)");
      appendTerminalLine("[SYSTEM] Fetching centralized logging records...", "system-line");
    });
  }

  if (rollbackBtn) {
    rollbackBtn.addEventListener("click", () => {
      showFlashNotification("Rolling back deployment to previous stable state...", "var(--gold-gauge)");
      appendTerminalLine("[SYSTEM] Initiating deployment rollback sequence to commit v1.2.5...", "info-line");
    });
  }

  if (systemCheckBtn) {
    systemCheckBtn.addEventListener("click", () => {
      showFlashNotification("Cluster diagnostic check completed. State: Healthy", "var(--teal-graph)");
      appendTerminalLine("[SYSTEM] Performing full cluster health check: 8/8 nodes operational.", "success-line");
    });
  }
}

// 3. Interactive SVG Chart Hover Tracking
function initInteractiveChart() {
  const chartContainer = document.querySelector(".chart-container");
  const chartSvg = document.querySelector(".chart-svg");
  const tooltip = document.getElementById("sys-chart-tooltip");
  const tooltipLine = document.getElementById("sys-tooltip-line");
  const cpuDot = document.getElementById("sys-cpu-dot");
  const memDot = document.getElementById("sys-mem-dot");

  if (!chartContainer || !chartSvg) return;

  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  chartContainer.addEventListener("mousemove", (e) => {
    const rect = chartSvg.getBoundingClientRect();
    const x = e.clientX - rect.left; // x coordinate relative to SVG container
    const svgWidth = rect.width;
    const svgHeight = rect.height;

    // Map x coordinates back to our SVG viewBox coordinates (0 to 700)
    const viewBoxX = (x / svgWidth) * 700;
    
    // Bounds check within margins (40 to 680)
    if (viewBoxX < 40 || viewBoxX > 680) {
      hideTooltip();
      return;
    }

    // Determine nearest month index (12 months spaced from 40 to 680)
    const interval = (680 - 40) / 11;
    const monthIdx = Math.round((viewBoxX - 40) / interval);
    const monthX = 40 + monthIdx * interval;

    // Simulate realistic historical CPU and Memory data values based on bezier paths
    const simulatedCpuVals = [35, 42, 60, 48, 55, 68, 62, 70, 52, 65, 58, 72];
    const simulatedMemVals = [48, 50, 55, 52, 58, 60, 54, 58, 62, 59, 64, 61];

    const cpuVal = simulatedCpuVals[monthIdx];
    const memVal = simulatedMemVals[monthIdx];

    // Compute y positions in SVG viewBox coordinates
    const cpuY = 160 - (cpuVal / 100) * 140; // 0-100% mapped to y: 160-20
    const memY = 160 - (memVal / 100) * 140;

    // Position tooltip elements
    tooltipLine.style.display = "block";
    tooltipLine.setAttribute("x1", monthX);
    tooltipLine.setAttribute("y1", 20);
    tooltipLine.setAttribute("x2", monthX);
    tooltipLine.setAttribute("y2", 160);

    cpuDot.style.display = "block";
    cpuDot.setAttribute("cx", monthX);
    cpuDot.setAttribute("cy", cpuY);

    memDot.style.display = "block";
    memDot.setAttribute("cx", monthX);
    memDot.setAttribute("cy", memY);

    // Update and show HTML Tooltip
    tooltip.style.display = "block";
    // Convert monthX back to client coordinates for absolute tooltip positioning
    const clientX = (monthX / 700) * svgWidth;
    tooltip.style.left = `${clientX + 10}px`;
    tooltip.style.top = `60px`;
    tooltip.innerHTML = `
      <div style="font-weight: 600; color: var(--text-gold-light); margin-bottom: 2px;">${months[monthIdx]} Telemetry</div>
      <div style="color: var(--teal-graph);">CPU: ${cpuVal}%</div>
      <div style="color: var(--purple-gauge);">Memory: ${memVal}%</div>
    `;
  });

  chartContainer.addEventListener("mouseleave", hideTooltip);

  function hideTooltip() {
    tooltip.style.display = "none";
    tooltipLine.style.display = "none";
    cpuDot.style.display = "none";
    memDot.style.display = "none";
  }
}

// Helper to append a line to the monospaced terminal
function appendTerminalLine(text, className = "") {
  const terminalBody = document.getElementById("agent-terminal-body");
  if (!terminalBody) return;

  const line = document.createElement("div");
  line.className = `terminal-line ${className}`;
  line.innerHTML = text;
  terminalBody.appendChild(line);

  // Auto-scroll to bottom
  terminalBody.scrollTop = terminalBody.scrollHeight;
}

// 4. Dynamic Pipeline Failure & Self-Healing Simulation Logic
let isSimulationRunning = false;

function initHealSimulation() {
  const simulateBtn = document.getElementById("btn-simulate-heal");
  if (!simulateBtn) return;

  simulateBtn.addEventListener("click", () => {
    if (isSimulationRunning) {
      showFlashNotification("Simulation already in progress...", "var(--gold-gauge)");
      return;
    }
    runHealSimulation();
  });
}

function runHealSimulation() {
  isSimulationRunning = true;
  
  // DOM Elements to mutate
  const simulateBtn = document.getElementById("btn-simulate-heal");
  const statusBadge = document.getElementById("system-status-badge");
  const statusBadgeText = statusBadge ? (statusBadge.querySelector(".status-text") || statusBadge.querySelector(".status-label")) : null;
  const statusDot = statusBadge ? (statusBadge.querySelector(".glowing-dot") || statusBadge.querySelector(".status-indicator-dot")) : null;
  const agentPulse = document.getElementById("agent-pulse");
  const agentStatusText = document.getElementById("agent-status-text");
  const terminalBody = document.getElementById("agent-terminal-body");
  const failedBuildsText = document.getElementById("failed-builds-val");
  const healingActionsText = document.getElementById("healing-actions-val");
  const activePodsText = document.getElementById("val-pods");
  const podMatrixGrid = document.getElementById("pod-matrix-grid");
  const cpuPercentText = document.getElementById("cpu-percent");
  const memoryPercentText = document.getElementById("memory-percent");
  const cpuCircle = document.getElementById("cpu-circle");
  const memoryCircle = document.getElementById("memory-circle");
  const runsTableBody = document.querySelector("#runs-table tbody");

  // Disable simulation button UI
  simulateBtn.style.opacity = "0.6";
  simulateBtn.style.cursor = "not-allowed";

  // Step 1: System Degrades (1 second)
  setTimeout(() => {
    // Mutate state to warning
    if (statusBadge) {
      statusBadge.style.borderColor = "rgba(248, 113, 113, 0.3)";
      statusBadge.style.background = "rgba(40, 20, 20, 0.4)";
      statusBadge.style.color = "#fca5a5";
    }
    if (statusDot) {
      statusDot.className = statusDot.classList.contains("status-indicator-dot") ? "status-indicator-dot offline" : "glowing-dot offline";
      statusDot.style.backgroundColor = "var(--red-failed)";
      statusDot.style.boxShadow = "0 0 8px var(--red-failed)";
    }
    if (statusBadgeText) statusBadgeText.textContent = "Degraded State";
    
    // Deactive 2 pods in cluster grid
    if (podMatrixGrid) {
      const dots = podMatrixGrid.querySelectorAll(".matrix-dot");
      if (dots.length >= 8) {
        dots[4].className = "matrix-dot offline pulse";
        dots[6].className = "matrix-dot offline pulse";
      }
    }
    if (activePodsText) activePodsText.innerHTML = `6<span class="val-sub">/8</span>`;

    // Spike System Telemetry
    if (cpuPercentText) cpuPercentText.textContent = "92%";
    updateCircleProgress(cpuCircle, 92);
    if (memoryPercentText) memoryPercentText.textContent = "84%";
    updateCircleProgress(memoryCircle, 84);

    // Increase failed builds
    if (failedBuildsText) {
      failedBuildsText.textContent = "3";
      failedBuildsText.style.color = "var(--red-failed)";
    }

    // Update Agent console status
    if (agentPulse) agentPulse.className = "status-pulse-dot active";
    if (agentStatusText) agentStatusText.textContent = "Agent Diagnostic Run";

    // Start logs printing
    if (terminalBody) terminalBody.innerHTML = ""; // Clear log
    appendTerminalLine("[AGENT] Pipeline failure warning received: RUN-4820 failed during build phase.", "error-line");
    appendTerminalLine("[AGENT] Triggering root cause diagnostics container...", "info-line");
  }, 1000);

  // Step 2: Fetch and analyze logs (2.5 seconds)
  setTimeout(() => {
    appendTerminalLine("[AGENT] Connected to logs pipe for container c-build-4820-x...", "system-line");
    appendTerminalLine("[AGENT] Error trace found: stderr output on task 'routes-compile':", "system-line");
    appendTerminalLine("  File \"app/routes/routes.py\", line 27<br>    return render_template(\"login.html\", error=\"Invalid username or password\"<br>                                                                           ^<br>SyntaxError: '{' was never closed", "error-line");
  }, 3500);

  // Step 3: Suggest code diff patch (5 seconds)
  setTimeout(() => {
    appendTerminalLine("[AGENT] Error identified: SyntaxError (unclosed parenthesis/brackets in routes.py).", "info-line");
    appendTerminalLine("[AGENT] Generating patch code changes...", "info-line");
    
    // Add diff box to terminal
    if (terminalBody) {
      const diffContainer = document.createElement("div");
      diffContainer.className = "code-diff-container";
      diffContainer.innerHTML = `
        <div class="diff-header">app/routes/routes.py (AI Code Patch suggestion)</div>
        <code class="diff-line diff-del">-    return render_template("login.html", error="Invalid username or password"</code>
        <code class="diff-line diff-ins">+    return render_template("login.html", error="Invalid username or password")</code>
      `;
      terminalBody.appendChild(diffContainer);
      terminalBody.scrollTop = terminalBody.scrollHeight;
    }
  }, 6000);

  // Step 4: Execute healing patch and build (8 seconds)
  setTimeout(() => {
    appendTerminalLine("[AGENT] Applying code patch to workspace branch 'patch/cortex-heal-4820'...", "info-line");
    appendTerminalLine("[AGENT] Triggering compilation and container build verification...", "system-line");
    appendTerminalLine("[AGENT] Output: 8/8 tests passed successfully.", "success-line");
    appendTerminalLine("[AGENT] Code verification status: VALIDATED.", "success-line");
  }, 9000);

  // Step 5: Merge and redeploy (10.5 seconds)
  setTimeout(() => {
    appendTerminalLine("[AGENT] Merging validated patch to main branch...", "info-line");
    appendTerminalLine("[AGENT] Triggering blue/green rolling deployment update...", "system-line");
    appendTerminalLine("[AGENT] Restarting failed pods in cluster...", "system-line");
    
    // Recover pod status dots in grid
    if (podMatrixGrid) {
      const dots = podMatrixGrid.querySelectorAll(".matrix-dot");
      if (dots.length >= 8) {
        setTimeout(() => { dots[4].className = "matrix-dot healthy"; }, 500);
        setTimeout(() => { dots[6].className = "matrix-dot healthy"; }, 1000);
      }
    }
  }, 11500);

  // Step 6: System complete heal (13 seconds)
  setTimeout(() => {
    // Restore header status UI
    if (statusBadge) {
      statusBadge.style.borderColor = "rgba(74, 222, 128, 0.3)";
      statusBadge.style.background = "rgba(20, 40, 25, 0.4)";
      statusBadge.style.color = "#86efac";
    }
    if (statusDot) {
      statusDot.className = statusDot.classList.contains("status-indicator-dot") ? "status-indicator-dot healthy" : "glowing-dot healthy";
      statusDot.style.backgroundColor = "var(--green-healthy)";
      statusDot.style.boxShadow = "0 0 8px var(--green-healthy)";
    }
    if (statusBadgeText) statusBadgeText.textContent = "Healthy";

    // Recover Pod numbers
    if (activePodsText) activePodsText.innerHTML = `8<span class="val-sub">/8</span>`;

    // Drop system telemetry back to normal
    if (cpuPercentText) cpuPercentText.textContent = "64%";
    updateCircleProgress(cpuCircle, 64);
    if (memoryPercentText) memoryPercentText.textContent = "58%";
    updateCircleProgress(memoryCircle, 58);

    // Increase healed actions count
    if (healingActionsText) healingActionsText.textContent = "16";

    // Add Healed entry to recent runs table
    const healedRow = document.createElement("tr");
    healedRow.id = "run-row-RUN-4820";
    healedRow.style.animation = "fadeInRow 0.5s ease-out";
    healedRow.innerHTML = `
      <td class="timeline-col">
        <div class="timeline-line"></div>
        <div class="timeline-node healed">
          <i class="fa-solid fa-bolt"></i>
        </div>
      </td>
      <td>
        <div class="deploy-info">
          <span class="deploy-name">RUN-4820 (main)</span>
          <span class="deploy-time">Just now</span>
        </div>
      </td>
      <td class="deploy-date">Manual</td>
      <td class="right-align">
        <span class="run-status-pill status-healed">Healed</span>
      </td>
    `;
    
    // Prepend row
    if (runsTableBody) {
      runsTableBody.insertBefore(healedRow, runsTableBody.firstChild);
    }

    // Reset agent status
    if (agentPulse) agentPulse.className = "status-pulse-dot idle";
    if (agentStatusText) agentStatusText.textContent = "Agent Idle";
    appendTerminalLine("[AGENT] Pipeline state recovered. System status: HEALED.", "success-line");

    // Enable simulate button
    simulateBtn.style.opacity = "1";
    simulateBtn.style.cursor = "pointer";
    isSimulationRunning = false;
    
    showFlashNotification("Pipeline RUN-4820 healed and deployed successfully!", "var(--green-healthy)");
  }, 14000);
}

// 5. Visual Toast Notification helper
function showFlashNotification(message, color) {
  const oldToast = document.querySelector(".dashboard-toast");
  if (oldToast) oldToast.remove();

  const toast = document.createElement("div");
  toast.className = "dashboard-toast glass-panel";
  toast.style.position = "fixed";
  toast.style.bottom = "20px";
  toast.style.right = "20px";
  toast.style.padding = "0.75rem 1.5rem";
  toast.style.zIndex = "1000";
  toast.style.borderLeft = `4px solid ${color}`;
  toast.style.animation = "slideIn 0.3s ease-out";
  toast.style.background = "rgba(26, 22, 20, 0.95)";
  toast.style.boxShadow = "0 4px 20px rgba(0, 0, 0, 0.6)";
  toast.style.color = "var(--text-gold-light)";
  toast.style.fontSize = "0.85rem";
  toast.style.display = "flex";
  toast.style.alignItems = "center";
  toast.style.gap = "0.5rem";
  
  toast.innerHTML = `<i class="fa-solid fa-circle-info" style="color: ${color}"></i> ${message}`;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = "slideOut 0.3s ease-in";
    toast.addEventListener("animationend", () => toast.remove());
  }, 3000);
}

// Add dynamic CSS keyframe animations for new elements to document head
const customStyles = document.createElement("style");
customStyles.textContent = `
  @keyframes fadeInRow {
    from { opacity: 0; transform: translateY(-10px); }
    to { opacity: 1; transform: translateY(0); }
  }
`;
document.head.appendChild(customStyles);

// Handle remediation timeline history actions
function initRemediationHistoryEvents() {
  const logBtns = document.querySelectorAll(".btn-logs");
  const traceBtns = document.querySelectorAll(".btn-trace");
  const serviceBtns = document.querySelectorAll(".btn-service");

  logBtns.forEach(btn => {
    btn.addEventListener("click", (e) => {
      const row = e.target.closest("tr");
      const eventName = row ? row.querySelector(".event-col").textContent : "event";
      showFlashNotification(`Retrieving remediation logs for: ${eventName}...`, "var(--purple-gauge)");
    });
  });

  traceBtns.forEach(btn => {
    btn.addEventListener("click", (e) => {
      const row = e.target.closest("tr");
      const eventName = row ? row.querySelector(".event-col").textContent : "event";
      showFlashNotification(`Generating root-cause trace report for: ${eventName}...`, "var(--teal-graph)");
    });
  });

  serviceBtns.forEach(btn => {
    btn.addEventListener("click", (e) => {
      const row = e.target.closest("tr");
      const eventName = row ? row.querySelector(".event-col").textContent : "event";
      const actionText = e.target.textContent.trim();
      showFlashNotification(`Triggering service action [${actionText}] for ${eventName}...`, "var(--gold-gauge)");
    });
  });
}

// -------------------------------------------------------------
// NEW SUB-DASHBOARD INTERACTIVE FEATURES
// -------------------------------------------------------------

// A. Logs Search and Filter
function initLogsSearchAndFilter() {
  const searchInput = document.getElementById("logs-search");
  const filterInfo = document.getElementById("filter-info");
  const filterWarning = document.getElementById("filter-warning");
  const filterError = document.getElementById("filter-error");
  const clearBtn = document.getElementById("btn-clear-filters");
  const tableRows = document.querySelectorAll("#logs-table-body tr");

  if (!tableRows.length) return;

  let activeFilters = {
    INFO: true,
    WARNING: true,
    ERROR: true
  };

  function applyFilters() {
    const query = searchInput ? searchInput.value.toLowerCase() : "";
    tableRows.forEach(row => {
      if (row.classList.contains("section-divider-row")) return; // Skip subheadings
      
      const badge = row.querySelector(".log-badge");
      const level = badge ? badge.textContent.trim() : "";
      const text = row.textContent.toLowerCase();

      const levelMatch = activeFilters[level] !== false;
      const textMatch = text.includes(query);

      if (levelMatch && textMatch) {
        row.style.display = "";
      } else {
        row.style.display = "none";
      }
    });
  }

  function setupFilterToggle(button, level) {
    if (!button) return;
    button.addEventListener("click", () => {
      button.classList.toggle("active");
      activeFilters[level] = button.classList.contains("active");
      applyFilters();
    });
  }

  setupFilterToggle(filterInfo, "INFO");
  setupFilterToggle(filterWarning, "WARNING");
  setupFilterToggle(filterError, "ERROR");

  if (searchInput) {
    searchInput.addEventListener("input", applyFilters);
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      if (searchInput) searchInput.value = "";
      [filterInfo, filterWarning, filterError].forEach(btn => {
        if (btn) btn.classList.add("active");
      });
      activeFilters = { INFO: true, WARNING: true, ERROR: true };
      applyFilters();
      showFlashNotification("Clear and reset all logs filters", "var(--text-gold-light)");
    });
  }
}

// B. Alerts Search and Category Filter
function initAlertsSearchAndFilter() {
  const selectFilter = document.querySelector(".flex-dropdown-alerts");
  const alertInput = document.getElementById("alert-search");
  const alertItems = document.querySelectorAll(".alerts-list-feed .alert-feed-item");

  if (!alertItems.length) return;

  function filterAlerts() {
    const selectVal = selectFilter ? selectFilter.value.toLowerCase() : "all";
    const query = alertInput ? alertInput.value.toLowerCase() : "";

    alertItems.forEach(item => {
      const text = item.textContent.toLowerCase();
      let typeMatch = false;

      if (selectVal.includes("all")) {
        typeMatch = true;
      } else if (selectVal.includes("critical") && item.classList.contains("critical")) {
        typeMatch = true;
      } else if (selectVal.includes("warning") && item.classList.contains("warning")) {
        typeMatch = true;
      } else if (selectVal.includes("info") && item.classList.contains("success")) {
        typeMatch = true;
      }

      const textMatch = text.includes(query);

      if (typeMatch && textMatch) {
        item.style.display = "";
      } else {
        item.style.display = "none";
      }
    });
  }

  if (selectFilter) selectFilter.addEventListener("change", filterAlerts);
  if (alertInput) alertInput.addEventListener("input", filterAlerts);
}

// C. Kubernetes Cluster Refresh Action
function initKubernetesActions() {
  const refreshBtn = document.querySelector(".page-actions-section .btn-refresh");
  const statusBadge = document.querySelector(".page-header-row + .cluster-status-section");

  if (!refreshBtn || !statusBadge) return;

  // Add click to refresh Kubernetes state
  refreshBtn.addEventListener("click", () => {
    // Spin icon
    const icon = refreshBtn.querySelector("i");
    if (icon) {
      icon.style.transition = "transform 0.6s ease-in-out";
      icon.style.transform = "rotate(360deg)";
      setTimeout(() => {
        icon.style.transition = "none";
        icon.style.transform = "rotate(0deg)";
      }, 600);
    }

    showFlashNotification("Syncing Kubernetes Cluster Resource metrics...", "var(--teal-graph)");

    // Find dials and status cards on kubernetes view
    const cpuDial = document.querySelector(".dial-card:nth-of-type(5) .dial-value");
    const cpuCircle = document.querySelector(".dial-card:nth-of-type(5) .circle-fill");
    const memDial = document.querySelector(".dial-card:nth-of-type(6) .dial-value");
    const memCircle = document.querySelector(".dial-card:nth-of-type(6) .circle-fill");

    if (cpuDial && cpuCircle) {
      const newCpu = Math.floor(Math.random() * 20) + 50; // 50-70%
      cpuDial.textContent = `${newCpu}%`;
      updateCircleProgress(cpuCircle, newCpu);
    }
    if (memDial && memCircle) {
      const newMem = Math.floor(Math.random() * 15) + 50; // 50-65%
      memDial.textContent = `${newMem}%`;
      updateCircleProgress(memCircle, newMem);
    }

    // Flash k8s pods list status tags
    const statusTags = document.querySelectorAll(".k8s-pods-table .status-indicator");
    statusTags.forEach(tag => {
      tag.style.opacity = "0.5";
      setTimeout(() => { tag.style.opacity = "1"; }, 300);
    });
  });
}

// D. AI Prediction Page Scaling Simulation
function initPredictionActions() {
  const executeBtn = document.getElementById("btn-execute-scaling");
  if (!executeBtn) return;

  executeBtn.addEventListener("click", () => {
    executeBtn.style.opacity = "0.6";
    executeBtn.style.cursor = "not-allowed";
    executeBtn.disabled = true;

    showFlashNotification("Executing automated scaling: adding +4 replicas to cluster...", "var(--purple-gauge)");

    const scaleArrowText = document.querySelector(".scale-value-text");
    const rightMatrixGrid = document.querySelector(".schematic-matrix-box:nth-of-type(3) .schematic-dots-grid");
    
    // Add pulsing warning state
    if (scaleArrowText) scaleArrowText.style.color = "var(--gold-gauge)";

    // Progressively light up scaling schematics
    if (rightMatrixGrid) {
      const dots = rightMatrixGrid.querySelectorAll(".schematic-dot");
      
      // Reset additional dots
      dots.forEach((dot, index) => {
        if (index >= 8) {
          dot.className = "schematic-dot";
        }
      });

      // Animate expansion
      setTimeout(() => {
        dots[8].className = "schematic-dot active pulsing-green";
      }, 1000);
      
      setTimeout(() => {
        dots[9].className = "schematic-dot active pulsing-green";
      }, 2000);

      setTimeout(() => {
        dots[10].className = "schematic-dot active pulsing-green";
      }, 3000);

      setTimeout(() => {
        dots[11].className = "schematic-dot active pulsing-green";
      }, 4000);
    }

    // Complete scaling process
    setTimeout(() => {
      if (scaleArrowText) scaleArrowText.textContent = "12 Replicas";
      showFlashNotification("Autoscaling complete: 12/12 active pod nodes verified healthy.", "var(--green-healthy)");
      
      // Update UI displays on prediction page
      const detailsDesc = document.querySelector(".prediction-card:nth-of-type(3) .prediction-details-desc");
      if (detailsDesc) detailsDesc.innerHTML = "Frontend scaled to 12 replicas. Load distributed.";

      executeBtn.style.opacity = "1";
      executeBtn.style.cursor = "pointer";
      executeBtn.disabled = false;
    }, 5500);
  });
}

// E. Deployments Namespace filtering & Action deck redeploy
function initDeploymentsActions() {
  const nsSelect = document.getElementById("deployments-namespace-select");
  const deploymentsGrid = document.getElementById("deployments-cards-grid");
  const actionButtons = document.querySelectorAll(".btn-deploy-action");

  if (nsSelect && deploymentsGrid) {
    nsSelect.addEventListener("change", () => {
      const ns = nsSelect.value;
      const cards = deploymentsGrid.querySelectorAll(".deployment-card-item");
      cards.forEach(card => {
        const cardNs = card.getAttribute("data-namespace");
        if (ns === "all" || cardNs === ns) {
          card.style.display = "";
        } else {
          card.style.display = "none";
        }
      });
      showFlashNotification(`Filter active namespaces: [${ns}]`, "var(--purple-gauge)");
    });
  }

  // Trigger deployment actions simulations
  actionButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const service = btn.getAttribute("data-service");
      const action = btn.getAttribute("data-action");

      if (action === "logs") {
        showFlashNotification(`Retrieving telemetry logging for ${service}...`, "var(--purple-gauge)");
      } else if (action === "rollback") {
        showFlashNotification(`Initiating Git rollback sequence for ${service}...`, "var(--red-failed)");
      } else if (action === "redeploy") {
        showFlashNotification(`Triggering automated redeployment container for ${service}...`, "var(--gold-gauge)");
        
        // Mutate target service card to simulate loading status
        const card = btn.closest(".deployment-card-item");
        if (card) {
          const statusDot = card.querySelector(".status-indicator-dot");
          const statusText = card.querySelector(".status-label");
          
          if (statusDot && statusText) {
            const originalDotClass = statusDot.className;
            const originalText = statusText.textContent;

            statusDot.className = "status-indicator-dot warning pulse";
            statusText.textContent = "Deploying";
            statusText.className = "status-label warning";

            setTimeout(() => {
              statusDot.className = "status-indicator-dot healthy";
              statusText.textContent = "Active";
              statusText.className = "status-label healthy";
              showFlashNotification(`Service ${service} deployed successfully!`, "var(--green-healthy)");
            }, 3000);
          }
        }
      }
    });
  });
}

// F. Pipeline Builder Node simulation sequence
function initPipelineActions() {
  const runBtn = document.getElementById("btn-run-pipeline");
  const retryBtn = document.getElementById("btn-retry-build");
  const rollbackBtn = document.getElementById("btn-rollback-build");
  const logScreen = document.getElementById("pipeline-console-logs-screen");
  
  const searchInput = document.getElementById("logs-console-search-input");
  const logPills = document.querySelectorAll(".log-pill-btn");
  
  if (!runBtn) return;

  // Append a line to the console screen
  function appendPipelineLog(text, level = "INFO", timestamp = "") {
    if (!logScreen) return;
    if (!timestamp) {
      const now = new Date();
      const hrs = String(now.getHours()).padStart(2, '0');
      const mins = String(now.getMinutes()).padStart(2, '0');
      const secs = String(now.getSeconds()).padStart(2, '0');
      timestamp = `${hrs}:${mins}:${secs}`;
    }
    
    const line = document.createElement("div");
    const lowercaseLevel = level.toLowerCase();
    line.className = `console-log-line ${lowercaseLevel}-line`;
    line.setAttribute("data-level", level);
    
    line.innerHTML = `<span class="log-timestamp">${timestamp}</span> <span class="log-badge-inline ${lowercaseLevel}">${level}</span> ${text}`;
    logScreen.appendChild(line);
    logScreen.scrollTop = logScreen.scrollHeight;
  }

  // Logs filters criteria
  let logFilterType = "all";
  function applyLogsFilter() {
    const lines = logScreen.querySelectorAll(".console-log-line");
    const query = searchInput ? searchInput.value.toLowerCase() : "";

    lines.forEach(line => {
      const text = line.textContent.toLowerCase();
      const level = line.getAttribute("data-level");
      
      const levelMatch = (logFilterType === "all" || level.toLowerCase() === logFilterType);
      const textMatch = text.includes(query);

      if (levelMatch && textMatch) {
        line.style.display = "";
      } else {
        line.style.display = "none";
      }
    });
  }

  if (searchInput) {
    searchInput.addEventListener("input", applyLogsFilter);
  }

  logPills.forEach(pill => {
    pill.addEventListener("click", () => {
      logPills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      logFilterType = pill.getAttribute("data-filter");
      applyLogsFilter();
    });
  });

  // Pipeline elements for UI updates
  const nodes = {
    commit: document.getElementById("node-code-commit"),
    checkout: document.getElementById("node-checkout"),
    build: document.getElementById("node-build"),
    test: document.getElementById("node-unit-tests"),
    docker: document.getElementById("node-docker-build"),
    scan: document.getElementById("node-image-scan"),
    push: document.getElementById("node-push-registry"),
    deploy: document.getElementById("node-deploy-k8s"),
    health: document.getElementById("node-health-check"),
    production: document.getElementById("node-production")
  };

  const conns = {
    commit: document.getElementById("conn-code-commit"),
    checkout: document.getElementById("conn-checkout"),
    build: document.getElementById("conn-build"),
    test: document.getElementById("conn-unit-tests"),
    docker: document.getElementById("conn-docker-build"),
    scan: document.getElementById("conn-image-scan"),
    push: document.getElementById("conn-push-registry"),
    deploy: document.getElementById("conn-deploy-k8s"),
    health: document.getElementById("conn-health-check")
  };

  const progressFill = document.getElementById("pipeline-progress-fill");
  const progressVal = document.getElementById("pipeline-progress-val");
  const currentStageText = document.getElementById("pipeline-current-stage-text");
  
  const statusBadge = document.getElementById("pipeline-status-badge");
  const infoStatusPill = document.getElementById("info-status-pill");
  
  const selfHealingTag = document.getElementById("self-healing-status-tag");
  const recoveryReason = document.getElementById("recovery-failure-reason");
  const recoveryAI = document.getElementById("recovery-ai-rec");
  const recoveryAction = document.getElementById("recovery-action-exec");
  const recoveryStatus = document.getElementById("recovery-status-value");
  const recoveryTime = document.getElementById("recovery-duration");
  const recoveryTimestamp = document.getElementById("recovery-timestamp");
  const shieldRing = document.getElementById("self-healing-shield-ring");
  const shieldIcon = document.getElementById("self-healing-shield-icon");

  function resetAllNodes() {
    Object.keys(nodes).forEach(key => {
      const node = nodes[key];
      if (node) {
        node.className = "flow-node waiting";
        const dot = node.querySelector(".flow-node-dot");
        if (dot) dot.innerHTML = `<i class="fa-solid fa-ellipsis"></i>`;
        const statusLabel = node.querySelector(".flow-node-status");
        if (statusLabel) statusLabel.textContent = "Waiting";
      }
    });

    Object.keys(conns).forEach(key => {
      const conn = conns[key];
      if (conn) conn.className = "flow-connector";
    });

    if (progressFill) progressFill.style.width = "0%";
    if (progressVal) progressVal.textContent = "0%";
    if (currentStageText) {
      currentStageText.textContent = "Code Commit Verification";
      currentStageText.className = "stage-highlight";
    }
    if (statusBadge) {
      statusBadge.textContent = "In Progress";
      statusBadge.className = "badge badge-info";
    }
    if (infoStatusPill) {
      infoStatusPill.textContent = "In Progress";
      infoStatusPill.className = "status-pill-info";
    }
  }

  function setNodeState(key, state) {
    const node = nodes[key];
    if (!node) return;
    
    node.className = `flow-node ${state}`;
    const dot = node.querySelector(".flow-node-dot");
    const statusLabel = node.querySelector(".flow-node-status");

    if (state === "success") {
      if (dot) dot.innerHTML = `<i class="fa-solid fa-check"></i>`;
      if (statusLabel) statusLabel.textContent = "Complete";
    } else if (state === "failed") {
      if (dot) dot.innerHTML = `<i class="fa-solid fa-xmark"></i>`;
      if (statusLabel) statusLabel.textContent = "Failed";
    } else if (state === "active") {
      if (dot) dot.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i>`;
      if (statusLabel) statusLabel.textContent = "Running";
    } else {
      if (dot) dot.innerHTML = `<i class="fa-solid fa-ellipsis"></i>`;
      if (statusLabel) statusLabel.textContent = "Waiting";
    }
  }

  function setConnectorState(key, state) {
    const conn = conns[key];
    if (conn) {
      conn.className = `flow-connector ${state}`;
    }
  }

  // 1. RUN PIPELINE SEQUENCE
  runBtn.addEventListener("click", () => {
    runBtn.disabled = true;
    retryBtn.disabled = true;
    rollbackBtn.disabled = true;
    runBtn.style.opacity = "0.5";
    
    resetAllNodes();
    if (logScreen) logScreen.innerHTML = "";
    showFlashNotification("Triggering CI/CD Pipeline run...", "var(--purple-gauge)");

    // Step 1: Code Commit
    setNodeState("commit", "active");
    appendPipelineLog("Initiating local repository repository-cortex analysis...", "INFO");
    
    setTimeout(() => {
      setNodeState("commit", "success");
      setConnectorState("commit", "success");
      appendPipelineLog("Code repository checkout verify: VALIDATED.", "INFO");
      
      // Step 2: Checkout
      setNodeState("checkout", "active");
      if (progressFill) progressFill.style.width = "10%";
      if (progressVal) progressVal.textContent = "10%";
      if (currentStageText) currentStageText.textContent = "Source Code Checkout";
      appendPipelineLog("Retrieving branch references: refs/heads/main...", "INFO");
    }, 1200);

    setTimeout(() => {
      setNodeState("checkout", "success");
      setConnectorState("checkout", "success");
      appendPipelineLog("Checked out commit c4ad2f1 (origin/main) successfully.", "INFO");
      
      // Step 3: Build
      setNodeState("build", "active");
      if (progressFill) progressFill.style.width = "20%";
      if (progressVal) progressVal.textContent = "20%";
      if (currentStageText) currentStageText.textContent = "Build Compilation";
      appendPipelineLog("Starting backend binary compilation and frontend web assets bundle compile...", "INFO");
    }, 2400);

    setTimeout(() => {
      setNodeState("build", "success");
      setConnectorState("build", "success");
      appendPipelineLog("Build compiled successfully in 1m 02s.", "INFO");
      
      // Step 4: Unit Tests
      setNodeState("test", "active");
      if (progressFill) progressFill.style.width = "35%";
      if (progressVal) progressVal.textContent = "35%";
      if (currentStageText) currentStageText.textContent = "Unit and Integration Testing";
      appendPipelineLog("Running pytest integration verification suite on dynamic sandbox...", "INFO");
    }, 3800);

    setTimeout(() => {
      setNodeState("test", "success");
      setConnectorState("test", "success");
      appendPipelineLog("Pytest suite finished: 24/24 test assertions passed.", "INFO");
      
      // Step 5: Docker Build
      setNodeState("docker", "active");
      if (progressFill) progressFill.style.width = "45%";
      if (progressVal) progressVal.textContent = "45%";
      if (currentStageText) currentStageText.textContent = "Container Image Build";
      appendPipelineLog("Compiling Docker layer steps. Building base layer caches...", "INFO");
    }, 5000);

    setTimeout(() => {
      setNodeState("docker", "success");
      setConnectorState("docker", "success");
      appendPipelineLog("Docker container compiled successfully: cortex-frontend-service:v1.2.6", "INFO");
      
      // Step 6: Image Scan
      setNodeState("scan", "active");
      if (progressFill) progressFill.style.width = "55%";
      if (progressVal) progressVal.textContent = "55%";
      if (currentStageText) currentStageText.textContent = "Security Auditing & Vulnerability Scan";
      appendPipelineLog("Initiating image container CVE analysis and security policy audit...", "INFO");
    }, 6200);

    setTimeout(() => {
      setNodeState("scan", "success");
      setConnectorState("scan", "success");
      appendPipelineLog("Security checks completed. 0 critical vulnerabilities, 2 warnings.", "INFO");
      
      // Step 7: Push Registry
      setNodeState("push", "active");
      if (progressFill) progressFill.style.width = "65%";
      if (progressVal) progressVal.textContent = "65%";
      if (currentStageText) currentStageText.textContent = "Pushing Docker Image to Registry";
      appendPipelineLog("Uploading image layers to registry.cortex-cicd.internal...", "INFO");
    }, 7400);

    setTimeout(() => {
      setNodeState("push", "success");
      setConnectorState("push", "success");
      appendPipelineLog("Image pushed successfully. Registry SHA: sha256:0d12acde32f...", "INFO");
      
      // Step 8: Deploy to K8s (Fails!)
      setNodeState("deploy", "active");
      if (progressFill) progressFill.style.width = "72%";
      if (progressVal) progressVal.textContent = "72%";
      if (currentStageText) {
        currentStageText.textContent = "Deploying to Kubernetes Cluster";
        currentStageText.className = "stage-highlight red-text";
      }
      appendPipelineLog("Triggering rolling update for deployment frontend-service in namespace production...", "INFO");
    }, 8600);

    setTimeout(() => {
      // Simulate Deploy failure
      setNodeState("deploy", "failed");
      appendPipelineLog("Kubernetes Pod Rollout Failed: containers failed to initialize.", "ERROR");
      appendPipelineLog("Readiness probe failed on pod cortex-frontend-8fbc923-2x1a", "ERROR");
      appendPipelineLog("WARN: Pod health state check is not ready (CrashLoopBackOff).", "WARN");
      appendPipelineLog("Deployment execution aborted. Triggering health checks status alerts...", "ERROR");
      
      if (statusBadge) {
        statusBadge.textContent = "Failed";
        statusBadge.className = "badge badge-failed";
      }
      if (infoStatusPill) {
        infoStatusPill.textContent = "Failed";
        infoStatusPill.className = "status-pill-failed";
      }
      
      // Modify Self-Healing Panel to simulate alert detection
      if (selfHealingTag) {
        selfHealingTag.textContent = "Failure Detected";
        selfHealingTag.className = "badge badge-red-outline";
      }
      if (recoveryReason) recoveryReason.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Readiness probe failed`;
      if (recoveryAI) recoveryAI.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Restart Deployment`;
      if (recoveryAction) recoveryAction.textContent = "Analyzing container states...";
      if (recoveryStatus) recoveryStatus.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Triggering AI Agent Recovery...`;
      if (shieldRing) shieldRing.className = "shield-glowing-ring failed pulse";
      
      showFlashNotification("Pipeline failure detected. AI Self-Healing container activated.", "var(--red-failed)");
      
      retryBtn.disabled = false;
      rollbackBtn.disabled = false;
      retryBtn.style.opacity = "1";
      rollbackBtn.style.opacity = "1";

      // 2. TRIGGER AUTOMATIC SELF-HEALING ACTION (3 seconds after failure)
      setTimeout(() => {
        simulateSelfHealing();
      }, 3500);

    }, 10200);
  });

  // Self-Healing Simulation Execution
  function simulateSelfHealing() {
    appendPipelineLog("[AGENT] Failure Alert Captured. Connected to c-frontend-8fbc923 log stream...", "INFO");
    appendPipelineLog("[AGENT] Diagnostics: readiness probe failed due to dynamic system resource starvation.", "WARN");
    appendPipelineLog("[AGENT] AI Healing Recommendation: Restart deployment configurations with custom timeout variables.", "INFO");
    
    if (recoveryAction) recoveryAction.textContent = "Restarting deployment config...";
    if (recoveryStatus) recoveryStatus.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Applying patch variables...`;
    
    setTimeout(() => {
      // Heal the failed stage node
      setNodeState("deploy", "success");
      const deployNode = nodes.deploy;
      if (deployNode) {
        const label = deployNode.querySelector(".flow-node-status");
        if (label) label.textContent = "Healed";
      }
      setConnectorState("deploy", "success");

      const badgeDeploy = document.getElementById("badge-stage-deploy");
      if (badgeDeploy) {
        badgeDeploy.textContent = "Healed";
        badgeDeploy.className = "stage-badge success";
      }

      appendPipelineLog("[AGENT] Restart deployment signal executed. Pod containers active and running.", "SUCCESS");
      appendPipelineLog("[AGENT] Pod readiness probe completed successfully.", "SUCCESS");

      // Resume Stages 9 and 10
      setNodeState("health", "active");
      if (progressFill) progressFill.style.width = "85%";
      if (progressVal) progressVal.textContent = "85%";
      if (currentStageText) {
        currentStageText.textContent = "Verifying Cluster Health Check";
        currentStageText.className = "stage-highlight";
      }
      appendPipelineLog("Pinging application health routing probes: http://frontend-service/health...", "INFO");

      setTimeout(() => {
        setNodeState("health", "success");
        setConnectorState("health", "success");
        appendPipelineLog("Application cluster health checks: 200 OK. State verified stable.", "SUCCESS");

        const badgeHealth = document.getElementById("badge-stage-health");
        if (badgeHealth) {
          badgeHealth.textContent = "Success";
          badgeHealth.className = "stage-badge success";
        }

        // Step 10: Production routing
        setNodeState("production", "active");
        if (progressFill) progressFill.style.width = "95%";
        if (progressVal) progressVal.textContent = "95%";
        if (currentStageText) currentStageText.textContent = "Active Production Release";
        appendPipelineLog("Updating ingress routing tables. Swapping build targets...", "INFO");
      }, 1500);

      setTimeout(() => {
        setNodeState("production", "success");
        if (progressFill) progressFill.style.width = "100%";
        if (progressVal) progressVal.textContent = "100%";
        
        const badgeProd = document.getElementById("badge-stage-production");
        if (badgeProd) {
          badgeProd.textContent = "Success";
          badgeProd.className = "stage-badge success";
        }

        appendPipelineLog("Active production traffic routed to release compilation #256.", "SUCCESS");
        appendPipelineLog("[SUCCESS] Pipeline Build #256 healed and deployed successfully!", "SUCCESS");

        // Set telemetry cards to healthy
        if (statusBadge) {
          statusBadge.textContent = "Success";
          statusBadge.className = "badge badge-success";
        }
        if (infoStatusPill) {
          infoStatusPill.textContent = "Success";
          infoStatusPill.className = "status-pill-success";
        }

        // Update Self Healing Card to Recovered Successfully
        if (selfHealingTag) {
          selfHealingTag.textContent = "Recovered Successfully";
          selfHealingTag.className = "badge badge-green-outline";
        }
        if (recoveryAction) recoveryAction.textContent = "Restarted deployment";
        if (recoveryStatus) recoveryStatus.innerHTML = `<i class="fa-solid fa-circle-check"></i> Recovered Successfully`;
        if (shieldRing) shieldRing.className = "shield-glowing-ring healthy";
        if (recoveryTime) recoveryTime.textContent = "27 sec";
        
        const now = new Date();
        const hrs = String(now.getHours()).padStart(2, '0');
        const mins = String(now.getMinutes()).padStart(2, '0');
        const secs = String(now.getSeconds()).padStart(2, '0');
        if (recoveryTimestamp) recoveryTimestamp.textContent = `${hrs}:${mins}:${secs}`;

        showFlashNotification("AI Healing recovery process completed: SUCCESS!", "var(--green-healthy)");

        runBtn.disabled = false;
        runBtn.style.opacity = "1";
      }, 3500);

    }, 2000);
  }

  // 2. RETRY FAILED BUILD
  retryBtn.addEventListener("click", () => {
    retryBtn.disabled = true;
    retryBtn.style.opacity = "0.5";
    showFlashNotification("Retrying failed build #256...", "var(--gold-gauge)");
    simulateSelfHealing();
  });

  // 3. ROLLBACK DEPLOYMENT
  rollbackBtn.addEventListener("click", () => {
    showFlashNotification("Triggering Git rollback sequence...", "var(--red-failed)");
    appendPipelineLog("Reverting configurations and ingress rules to release v1.2.5...", "WARN");
    appendPipelineLog("Rolling back deployment container layers to target sha256:d55fbc...", "WARN");
    setTimeout(() => {
      appendPipelineLog("[SUCCESS] Rollback completed. Stable release online.", "SUCCESS");
    }, 1500);
  });
}


// G. Settings Form Toggles and Save
function initSettingsActions() {
  const saveBtn = document.querySelector(".btn-save-settings");
  const toggles = document.querySelectorAll(".custom-toggle-btn input");

  if (saveBtn) {
    saveBtn.addEventListener("click", (e) => {
      e.preventDefault();
      showFlashNotification("Saving platform preferences to .planning/config.json...", "var(--gold-gauge)");
      setTimeout(() => {
        showFlashNotification("Platform settings updated and configurations synced!", "var(--green-healthy)");
      }, 1500);
    });
  }

  toggles.forEach(toggle => {
    toggle.addEventListener("change", () => {
      const label = toggle.closest(".settings-control-item").querySelector(".settings-item-main-title").textContent;
      const stateText = toggle.checked ? "ON" : "OFF";
      
      // Update label text if track label element is found
      const trackLabel = toggle.nextElementSibling.querySelector(".toggle-text-label");
      if (trackLabel) trackLabel.textContent = stateText;

      showFlashNotification(`Updated: ${label} is now [${stateText}]`, "var(--purple-gauge)");
    });
  });
}

// -------------------------------------------------------------
// GLOBAL BUTTON INTERACTIVITY & LAYOUT RESPONSIVENESS HANDLERS
// -------------------------------------------------------------
function initGlobalButtonActions() {
  // 1. Sidebar Collapse Toggle (Hamburger Menu Button)
  const navToggleBtn = document.querySelector(".nav-toggle-btn");
  const appContainer = document.querySelector(".app-container");
  if (navToggleBtn && appContainer) {
    navToggleBtn.addEventListener("click", () => {
      appContainer.classList.toggle("sidebar-collapsed");
      const isCollapsed = appContainer.classList.contains("sidebar-collapsed");
      showFlashNotification(isCollapsed ? "Sidebar minimized for expanded layout" : "Sidebar expanded", "var(--teal-graph)");
    });
  }

  // 2. Top Navbar Bell & Help Icon Buttons
  const iconNavButtons = document.querySelectorAll(".icon-nav-btn");
  iconNavButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const icon = btn.querySelector("i");
      if (icon && icon.classList.contains("fa-bell")) {
        showInteractiveModal("Real-Time System Alerts Center", `
          <div style="display: flex; flex-direction: column; gap: 1rem;">
            <div class="alert-feed-item critical" style="margin: 0; display: flex; align-items: center; gap: 1rem;">
              <div class="alert-icon-wrapper bg-red"><i class="fa-solid fa-circle-xmark"></i></div>
              <div>
                <h4 style="color: var(--red-failed); margin-bottom: 0.2rem;">Deployment Readiness Timeout</h4>
                <p style="font-size: 0.8rem; color: var(--text-secondary);">frontend-service (US-East-1) failed health check probe.</p>
              </div>
            </div>
            <div class="alert-feed-item warning-alert" style="margin: 0; display: flex; align-items: center; gap: 1rem;">
              <div class="alert-icon-wrapper bg-gold"><i class="fa-solid fa-circle-exclamation"></i></div>
              <div>
                <h4 style="color: var(--gold-gauge); margin-bottom: 0.2rem;">CPU Usage Spike Detected</h4>
                <p style="font-size: 0.8rem; color: var(--text-secondary);">Node k8s-worker-03 running at 88% capacity.</p>
              </div>
            </div>
            <div class="alert-feed-item info" style="margin: 0; display: flex; align-items: center; gap: 1rem;">
              <div class="alert-icon-wrapper bg-teal"><i class="fa-solid fa-circle-info"></i></div>
              <div>
                <h4 style="color: var(--teal-graph); margin-bottom: 0.2rem;">Autonomous Self-Healing Active</h4>
                <p style="font-size: 0.8rem; color: var(--text-secondary);">Agent cortex-bot-v4 ready for automated patch synthesis.</p>
              </div>
            </div>
          </div>
        `, [
          { text: "Dismiss All Alerts", color: "var(--red-failed)", action: () => showFlashNotification("All active alerts acknowledged and dismissed.", "var(--green-healthy)") },
          { text: "Open Alerts Console", color: "var(--teal-graph)", action: () => { window.location.href = "/alerts"; } }
        ]);
      } else if (icon && icon.classList.contains("fa-circle-question")) {
        showInteractiveModal("Cortex AI Self-Healing Quickstart Guide", `
          <div style="display: flex; flex-direction: column; gap: 1rem; color: var(--text-secondary); font-size: 0.9rem;">
            <p><strong style="color: var(--text-gold-light);">Welcome to Cortex CI/CD!</strong> Our platform monitors pipeline builds, Kubernetes clusters, and deployment traffic in real-time.</p>
            <div style="background: rgba(0,0,0,0.3); padding: 1rem; border-radius: 8px; border-left: 3px solid var(--purple-gauge);">
              <h5 style="color: #fff; margin-bottom: 0.4rem;"><i class="fa-solid fa-wand-magic-sparkles"></i> How Self-Healing Works:</h5>
              <ol style="padding-left: 1.2rem; display: flex; flex-direction: column; gap: 0.4rem;">
                <li>When a build fails, the AI Agent connects to diagnostic container stderr logs.</li>
                <li>The autonomous engine parses syntax errors, unclosed brackets, and broken imports.</li>
                <li>An automated code diff patch is generated, validated inside an isolated sandbox, and pushed to main.</li>
                <li>Kubernetes pods are automatically restarted with zero downtime.</li>
              </ol>
            </div>
            <p><strong style="color: var(--teal-graph);">Pro-Tip:</strong> Click <code style="color: var(--gold-gauge);">Simulate Failure & Heal</code> on the Dashboard to watch the live terminal reasoning right now!</p>
          </div>
        `, [
          { text: "Got It", color: "var(--purple-gauge)", action: () => {} }
        ]);
      }
    });
  });

  // 3. User Profile Popover Menu
  const profileContainer = document.querySelector(".nav-user-profile");
  if (profileContainer) {
    profileContainer.addEventListener("click", (e) => {
      e.stopPropagation();
      let existingMenu = document.querySelector(".profile-dropdown-menu");
      if (existingMenu) {
        existingMenu.remove();
        return;
      }
      const menu = document.createElement("div");
      menu.className = "profile-dropdown-menu";
      menu.innerHTML = `
        <div style="padding: 0.5rem 1.25rem; font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px;">Workspace: Production</div>
        <div class="profile-menu-item" onclick="window.location.href='/settings'"><i class="fa-solid fa-user-gear"></i> Account & Settings</div>
        <div class="profile-menu-item" onclick="showFlashNotification('API Key: ctx_live_99482701a... copied to clipboard!', 'var(--teal-graph)')"><i class="fa-solid fa-key"></i> Copy API Key</div>
        <div class="profile-menu-item" onclick="showFlashNotification('Switched to Staging Environment scope', 'var(--purple-gauge)')"><i class="fa-solid fa-layer-group"></i> Switch Environment</div>
        <div class="profile-menu-divider"></div>
        <div class="profile-menu-item" style="color: var(--red-failed);" onclick="window.location.href='/logout'"><i class="fa-solid fa-right-from-bracket"></i> Log Out</div>
      `;
      document.body.appendChild(menu);

      const closeMenu = (event) => {
        if (!menu.contains(event.target)) {
          menu.remove();
          document.removeEventListener("click", closeMenu);
        }
      };
      setTimeout(() => document.addEventListener("click", closeMenu), 10);
    });
  }

  // 4. Global Search Bar Interactions
  const searchContainer = document.querySelector(".search-box-container");
  const searchInput = document.querySelector(".top-search-input");
  if (searchContainer && searchInput) {
    const triggerSearch = () => {
      const query = searchInput.value.trim();
      if (!query) {
        showFlashNotification("Please enter a search keyword (e.g., 'RUN-4820', 'pod', 'error')", "var(--gold-gauge)");
        return;
      }
      showInteractiveModal(`Search Results: "${query}"`, `
        <div style="display: flex; flex-direction: column; gap: 0.8rem;">
          <div class="dashboard-card" style="margin: 0; padding: 0.8rem 1rem; cursor: pointer;" onclick="window.location.href='/pipeline'">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-weight: 600; color: var(--text-gold-light);"><i class="fa-solid fa-rocket" style="color: var(--purple-gauge);"></i> Pipeline RUN-4820 (main)</span>
              <span class="run-status-pill status-healed">Healed</span>
            </div>
            <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.3rem;">Found match in build logs and AI self-healing diagnostics patch.</div>
          </div>
          <div class="dashboard-card" style="margin: 0; padding: 0.8rem 1rem; cursor: pointer;" onclick="window.location.href='/deployments'">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-weight: 600; color: var(--text-gold-light);"><i class="fa-solid fa-box" style="color: var(--teal-graph);"></i> frontend-service (v1.2.6)</span>
              <span class="status-label healthy">4/4 Running</span>
            </div>
            <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.3rem;">Production namespace deployment config match.</div>
          </div>
          <div class="dashboard-card" style="margin: 0; padding: 0.8rem 1rem; cursor: pointer;" onclick="window.location.href='/logs'">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-weight: 600; color: var(--text-gold-light);"><i class="fa-solid fa-file-lines" style="color: var(--gold-gauge);"></i> Container Error Trace</span>
              <span class="log-badge error">ERROR</span>
            </div>
            <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.3rem;">SyntaxError: unclosed parenthesis in routes.py (Line 27).</div>
          </div>
        </div>
      `, [{ text: "Close Search", color: "var(--text-secondary)", action: () => {} }]);
    };

    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") triggerSearch();
    });
    const searchIcon = searchContainer.querySelector(".search-icon");
    if (searchIcon) {
      searchIcon.style.cursor = "pointer";
      searchIcon.addEventListener("click", triggerSearch);
    }
  }

  // 5. All Refresh Buttons (.btn-refresh)
  const refreshButtons = document.querySelectorAll(".btn-refresh");
  refreshButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const icon = btn.querySelector("i");
      if (icon) {
        icon.style.transition = "transform 0.6s cubic-bezier(0.4, 0, 0.2, 1)";
        icon.style.transform = "rotate(360deg)";
        setTimeout(() => {
          icon.style.transition = "none";
          icon.style.transform = "rotate(0deg)";
        }, 600);
      }
      showFlashNotification("System telemetry metrics synced successfully across all nodes.", "var(--teal-graph)");
    });
  });

  // 6. Table Row & Card Ellipsis More Buttons (.icon-btn-more)
  const moreButtons = document.querySelectorAll(".icon-btn-more");
  moreButtons.forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const row = btn.closest("tr") || btn.closest(".dashboard-card");
      const title = row ? (row.querySelector("td:nth-child(1)") || row.querySelector("h3") || row).textContent.trim().split("\n")[0] : "Resource Item";
      showInteractiveModal(`Resource Inspector: ${title}`, `
        <div style="display: flex; flex-direction: column; gap: 0.75rem; font-family: 'Fira Code', monospace; font-size: 0.85rem; color: var(--text-white);">
          <div style="background: rgba(0,0,0,0.4); padding: 0.8rem; border-radius: 6px; border: 1px solid rgba(229,193,138,0.15);">
            <div><span style="color: var(--purple-gauge);">Resource UUID:</span> 8fbc923-a12b-491a-9821</div>
            <div><span style="color: var(--teal-graph);">Cluster IP:</span> 10.244.1.104</div>
            <div><span style="color: var(--gold-gauge);">Memory Limit:</span> 2048 MiB / CPU: 500m</div>
            <div><span style="color: var(--green-healthy);">Health Probe:</span> HTTP GET /healthz -> 200 OK</div>
          </div>
          <div style="color: var(--text-secondary); font-family: 'Inter', sans-serif; font-size: 0.85rem;">Choose an immediate diagnostic action for this container:</div>
        </div>
      `, [
        { text: "Restart Instance", color: "var(--gold-gauge)", action: () => showFlashNotification(`Restart signal sent for ${title}`, "var(--green-healthy)") },
        { text: "Extract Stack Trace", color: "var(--purple-gauge)", action: () => showFlashNotification(`Stack trace extracted to diagnostic terminal.`, "var(--teal-graph)") },
        { text: "Close", color: "var(--text-secondary)", action: () => {} }
      ]);
    });
  });

  // 7. Time/Date Filters (#btn-time-filter, #btn-date-filter, .graph-time-select)
  const timeFilters = document.querySelectorAll("#btn-time-filter, #btn-date-filter");
  const optionsList = ["Last 15 Minutes", "Last 1 Hour", "Last 6 Hours", "Last 24 Hours", "Last 7 Days"];
  timeFilters.forEach(btn => {
    btn.addEventListener("click", () => {
      const span = btn.querySelector("span");
      if (span) {
        let idx = optionsList.indexOf(span.textContent.trim());
        idx = (idx + 1) % optionsList.length;
        span.textContent = optionsList[idx];
        showFlashNotification(`Time horizon filter shifted to: [${optionsList[idx]}]`, "var(--purple-gauge)");
      }
    });
  });

  const graphSelects = document.querySelectorAll(".graph-time-select, #pipeline-time-filter");
  graphSelects.forEach(sel => {
    sel.addEventListener("change", () => {
      showFlashNotification(`Graph data horizon re-sampled for: ${sel.value || sel.options[sel.selectedIndex].text}`, "var(--teal-graph)");
    });
  });

  // 8. View Alerts Button (#btn-view-alerts) across Monitoring / K8s pages
  const viewAlertsBtns = document.querySelectorAll("#btn-view-alerts");
  viewAlertsBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      window.location.href = "/alerts";
    });
  });

  // 9. Pagination Buttons (.btn-pagination)
  const pageBtns = document.querySelectorAll(".btn-pagination");
  pageBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      pageBtns.forEach(b => b.classList.remove("active"));
      if (!btn.querySelector("i")) btn.classList.add("active");
      const text = btn.textContent.trim() || "Next";
      showFlashNotification(`Displaying log stream window: Page ${text}`, "var(--gold-gauge)");
      const tableBody = document.querySelector("#logs-table-body");
      if (tableBody) tableBody.scrollIntoView({ behavior: "smooth" });
    });
  });

  // 10. Self-Healing Timeline Filter Pills (.filter-pill)
  const filterPills = document.querySelectorAll(".filter-pill");
  filterPills.forEach(pill => {
    pill.addEventListener("click", () => {
      filterPills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      const filterText = pill.textContent.trim().toLowerCase();
      
      const cards = document.querySelectorAll(".timeline-event-card");
      cards.forEach(card => {
        const actionTitle = card.querySelector(".event-action-title");
        if (!actionTitle) return;
        const titleText = actionTitle.textContent.trim().toLowerCase();
        if (filterText.includes("all") || titleText.includes(filterText) || filterText.includes(titleText)) {
          card.style.display = "";
        } else {
          card.style.display = "none";
        }
      });
      showFlashNotification(`Remediation history filtered by type: [${pill.textContent.trim()}]`, "var(--green-healthy)");
    });
  });

  // 11. Alerts Page Card Click Handlers
  const alertItems = document.querySelectorAll(".alert-feed-item");
  alertItems.forEach(item => {
    item.style.cursor = "pointer";
    item.addEventListener("click", () => {
      const title = item.querySelector(".alert-title-text") ? item.querySelector(".alert-title-text").textContent : "Incident Alert";
      const desc = item.querySelector(".alert-desc-text") ? item.querySelector(".alert-desc-text").textContent : "";
      showInteractiveModal(`Incident Management: ${title}`, `
        <div style="display: flex; flex-direction: column; gap: 1rem; color: var(--text-white);">
          <div style="padding: 1rem; background: rgba(0,0,0,0.35); border-radius: 8px; border-left: 4px solid var(--gold-gauge);">
            <p style="margin: 0; font-size: 0.9rem; color: var(--text-gold-light);">${desc}</p>
          </div>
          <p style="font-size: 0.85rem; color: var(--text-secondary);">Select mitigation routine for this telemetry alert:</p>
        </div>
      `, [
        { text: "Acknowledge & Silence", color: "var(--teal-graph)", action: () => {
          item.style.opacity = "0.45";
          showFlashNotification(`Alert "${title}" silenced and acknowledged.`, "var(--green-healthy)");
        } },
        { text: "Create PagerDuty Incident", color: "var(--gold-gauge)", action: () => showFlashNotification(`PagerDuty ticket INC-9481 created and assigned to on-call SRE.`, "var(--purple-gauge)") },
        { text: "Close", color: "var(--text-secondary)", action: () => {} }
      ]);
    });
  });

  // 12. Settings Select Boxes (.settings-action-select)
  const settingsSelects = document.querySelectorAll(".settings-action-select");
  settingsSelects.forEach(sel => {
    sel.addEventListener("change", () => {
      showFlashNotification(`Automation behavior set to: [${sel.value}]`, "var(--purple-gauge)");
    });
  });
}

// Helper to display generic modal
function showInteractiveModal(titleText, bodyHtml, buttonsArray = []) {
  const oldModal = document.querySelector(".interactive-modal-overlay");
  if (oldModal) oldModal.remove();

  const overlay = document.createElement("div");
  overlay.className = "interactive-modal-overlay";

  const box = document.createElement("div");
  box.className = "interactive-modal-box";

  let buttonsHtml = "";
  buttonsArray.forEach((btn, index) => {
    buttonsHtml += `<button class="btn" style="background: ${btn.color}; color: #110e0c; font-weight: 600; padding: 0.5rem 1.25rem; border: none; border-radius: 6px;" id="modal-btn-${index}">${btn.text}</button>`;
  });

  box.innerHTML = `
    <div class="modal-header">
      <div class="modal-title"><i class="fa-solid fa-layer-group" style="color: var(--teal-graph);"></i> ${titleText}</div>
      <button class="modal-close-btn"><i class="fa-solid fa-xmark"></i></button>
    </div>
    <div class="modal-body">${bodyHtml}</div>
    <div class="modal-footer">${buttonsHtml}</div>
  `;

  overlay.appendChild(box);
  document.body.appendChild(overlay);

  const closeBtn = box.querySelector(".modal-close-btn");
  closeBtn.addEventListener("click", () => overlay.remove());
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });

  buttonsArray.forEach((btn, index) => {
    const el = box.querySelector(`#modal-btn-${index}`);
    if (el && btn.action) {
      el.addEventListener("click", () => {
        btn.action();
        overlay.remove();
      });
    }
  });
}

