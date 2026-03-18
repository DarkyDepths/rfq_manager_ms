// GHI Tender Manager - Global App Logic

document.addEventListener("DOMContentLoaded", () => {
  // =======================================
  // 1) Init progress bars (all pages)
  // =======================================
  document.querySelectorAll(".progress-bar").forEach((bar) => {
    const value = bar.getAttribute("data-progress");
    const fill = bar.querySelector(".progress-bar-fill");
    if (fill && value !== null) {
      requestAnimationFrame(() => {
        fill.style.width = value + "%";
      });
    }
  });

  // =======================================
  // 2) Tabs (workspace or other tabbed views)
  // =======================================
  document.querySelectorAll("[data-tabs]").forEach((tabsContainer) => {
    const tabs = tabsContainer.querySelectorAll(".tab");
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const targetId = tab.getAttribute("data-tab-target");
        if (!targetId) return;
        const panel = document.getElementById(targetId);

        // deactivate all
        tabs.forEach((t) => t.classList.remove("active"));
        document
          .querySelectorAll(".tab-panel")
          .forEach((p) => p.classList.remove("active"));

        tab.classList.add("active");
        if (panel) {
          panel.classList.add("active");
        }
      });
    });
  });

  // =======================================

// Activate tab based on URL hash (e.g. workspace.html#stage-boq-bom)
const hash = window.location.hash ? window.location.hash.slice(1) : "";
if (hash) {
  const targetPanel = document.getElementById(hash);
  if (targetPanel) {
    const tabsContainer = targetPanel.closest("[data-tabs]");
    if (tabsContainer) {
      const tabs = tabsContainer.querySelectorAll(".tab");
      const panels = tabsContainer.querySelectorAll(".tab-panel");
      const targetTab = tabsContainer.querySelector(
        `.tab[data-tab-target="${hash}"]`
      );
      if (targetTab) {
        tabs.forEach((t) => t.classList.remove("active"));
        panels.forEach((p) => p.classList.remove("active"));
        targetTab.classList.add("active");
        targetPanel.classList.add("active");
      }
    }
  }
}

  // 3) Create RFQ page logic (workflow + auto timeline)
  //    This code is defensive: it only runs if elements exist.
  // =======================================

  const prioritySelect = document.getElementById("priority");
  const prioritySummary = document.getElementById("summary-priority");

  // Sync priority to KPI card (if present)
  if (prioritySelect && prioritySummary) {
    const syncPriority = () => {
      const text =
        prioritySelect.options[prioritySelect.selectedIndex]?.text || "Normal";
      prioritySummary.textContent = text;
    };
    syncPriority();
    prioritySelect.addEventListener("change", syncPriority);
  }

  // Elements specific to the Create RFQ page
  const workflowRadios = document.querySelectorAll(".workflow-radio");
  const chipLong = document.getElementById("chip-long");
  const chipShort = document.getElementById("chip-short");
  const chipCustom = document.getElementById("chip-custom");
  const customPanel = document.getElementById("custom-stages-panel");
  const customStageCheckboxes = document.querySelectorAll(".custom-stage");
  const summaryWorkflowType = document.getElementById("summary-workflow-type");
  const summaryWorkflowDetail = document.getElementById(
    "summary-workflow-detail"
  );
  const summaryCurrentStage = document.getElementById("summary-current-stage");
  const summaryStagePosition = document.getElementById("summary-stage-position");
  const timelineContainer = document.getElementById("timeline-container");
  const deadlineInput = document.getElementById("deadline");

  // If not on the Create RFQ page, don't run the rest
  const isCreateRFQPage =
    workflowRadios.length > 0 && timelineContainer !== null;

  if (!isCreateRFQPage) {
    return;
  }

  // ----------------------
  // Helper functions
  // ----------------------

  function getTodayAtMidnight() {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }

  function parseDateInput(inputEl) {
    if (!inputEl || !inputEl.value) return null;
    const d = new Date(inputEl.value);
    if (Number.isNaN(d.getTime())) return null;
    d.setHours(0, 0, 0, 0);
    return d;
  }

  function formatDateISO(d) {
    if (!(d instanceof Date) || Number.isNaN(d.getTime())) return "";
    return d.toISOString().slice(0, 10);
  }

  function getLongWorkflowStages() {
    return [
      "RFQ received",
      "Go / No-Go",
      "Pre-bid clarifications",
      "Preliminary design",
      "BOQ / BOM preparation",
      "Vendor inquiry",
      "Cost estimation",
      "Internal approval",
      "Offer submission",
      "Post-bid clarifications",
      "Award / Lost",
    ];
  }

  function getShortWorkflowStages() {
    return [
      "RFQ received",
      "Cost estimation",
      "Internal approval",
      "Offer submission",
      "Award / Lost",
    ];
  }

  function getCustomWorkflowStages() {
    const stages = [];
    customStageCheckboxes.forEach((cb) => {
      if (cb.checked) {
        stages.push(cb.value);
      }
    });
    return stages;
  }

  /**
   * Returns only the stages we want to plan between start date and deadline.
   * Typically all stages from the second until "Offer submission" included,
   * since "RFQ received" is instantaneous and "Post-bid" / "Award" are after the deadline.
   */
  function getPlannedStagesForDates(allStages) {
    if (!allStages || allStages.length === 0) return [];

    // If there is an "Offer submission", stop there.
    const offerIndex = allStages.indexOf("Offer submission");
    const cutIndex = offerIndex >= 0 ? offerIndex + 1 : allStages.length;

    // We exclude "RFQ received" from time distribution if present at index 0.
    if (allStages[0] === "RFQ received") {
      return allStages.slice(1, cutIndex);
    }

    return allStages.slice(0, cutIndex);
  }

  /**
   * Compute planned date intervals for each planned stage.
   * Returns an object: { [stageName]: { start: Date, end: Date } }
   */
  function computeStageDateMap(allStages, startDate, deadlineDate) {
    const map = {};
    if (!startDate || !deadlineDate) return map;

    // Only plan a subset of stages (before deadline)
    const plannedStages = getPlannedStagesForDates(allStages);
    const n = plannedStages.length;
    if (n === 0) return map;

    const msPerDay = 1000 * 60 * 60 * 24;
    const diffDaysRaw = (deadlineDate - startDate) / msPerDay;
    // Guarantee at least 1 day per stage
    const totalDays = Math.max(diffDaysRaw, n);

    for (let k = 0; k < n; k++) {
      const s = new Date(startDate.getTime());
      s.setDate(s.getDate() + Math.floor((totalDays * k) / n));

      const e = new Date(startDate.getTime());
      e.setDate(e.getDate() + Math.floor((totalDays * (k + 1)) / n));

      map[plannedStages[k]] = { start: s, end: e };
    }

    return map;
  }

  function renderTimeline(allStages, startDate, deadlineDate) {
    if (!timelineContainer) return;
    timelineContainer.innerHTML = "";

    const stageDateMap = computeStageDateMap(allStages, startDate, deadlineDate);
    const hasDates = Object.keys(stageDateMap).length > 0;

    allStages.forEach((stage, index) => {
      const item = document.createElement("div");
      item.className =
        "timeline-item" + (index === 0 ? " timeline-item-active" : "");

      const label = document.createElement("div");
      label.className = "timeline-label";
      label.textContent = stage;

      const meta = document.createElement("div");
      meta.className = "timeline-meta";

      if (index === 0) {
        // First stage (usually "RFQ received")
        if (hasDates && stageDateMap[stage]) {
          const { start, end } = stageDateMap[stage];
          meta.textContent =
            "Current stage at creation – " +
            formatDateISO(start) +
            " → " +
            formatDateISO(end);
        } else {
          meta.textContent = "Current stage at creation (0% completed)";
        }
      } else {
        if (hasDates && stageDateMap[stage]) {
          const { start, end } = stageDateMap[stage];
          let suffix = "";
          if (deadlineDate && formatDateISO(end) === formatDateISO(deadlineDate)) {
            suffix = " (client deadline)";
          }
          meta.textContent =
            "Planned: " +
            formatDateISO(start) +
            " → " +
            formatDateISO(end) +
            suffix;
        } else {
          meta.textContent = "Planned stage " + (index + 1);
        }
      }

      item.appendChild(label);
      item.appendChild(meta);
      timelineContainer.appendChild(item);
    });
  }

  function updateSummaryForWorkflow(type) {
    let stages;
    if (type === "long") {
      stages = getLongWorkflowStages();
      if (summaryWorkflowType) {
        summaryWorkflowType.textContent = "GHI long workflow";
      }
      if (summaryWorkflowDetail) {
        summaryWorkflowDetail.textContent =
          stages.length + " stages – full lifecycle";
      }
    } else if (type === "short") {
      stages = getShortWorkflowStages();
      if (summaryWorkflowType) {
        summaryWorkflowType.textContent = "GHI short workflow";
      }
      if (summaryWorkflowDetail) {
        summaryWorkflowDetail.textContent =
          stages.length + " stages – simplified";
      }
    } else {
      stages = getCustomWorkflowStages();
      if (summaryWorkflowType) {
        summaryWorkflowType.textContent = "Custom workflow";
      }
      if (summaryWorkflowDetail) {
        summaryWorkflowDetail.textContent =
          stages.length + " selected stages";
      }
    }

    if (stages.length > 0) {
      if (summaryCurrentStage) {
        summaryCurrentStage.textContent = stages[0];
      }
      if (summaryStagePosition) {
        summaryStagePosition.textContent = "Stage 1 of " + stages.length;
      }
    } else {
      if (summaryCurrentStage) {
        summaryCurrentStage.textContent = "No stages selected";
      }
      if (summaryStagePosition) {
        summaryStagePosition.textContent = "";
      }
    }

    // Compute timeline dates based on deadline (if any)
    const startDate = getTodayAtMidnight(); // date de création du RFQ (simplifiée)
    const deadlineDate = parseDateInput(deadlineInput);

    renderTimeline(stages, startDate, deadlineDate);
  }

  function refreshSelectionVisual(type) {
    if (chipLong) chipLong.style.display = type === "long" ? "inline-block" : "none";
    if (chipShort) chipShort.style.display = type === "short" ? "inline-block" : "none";
    if (chipCustom) chipCustom.style.display = type === "custom" ? "inline-block" : "none";
    if (customPanel) customPanel.style.display = type === "custom" ? "block" : "none";
  }

  // ----------------------
  // Event bindings
  // ----------------------

  // Workflow radio buttons
  workflowRadios.forEach((radio) => {
    radio.addEventListener("change", function () {
      const type = this.value;
      refreshSelectionVisual(type);
      updateSummaryForWorkflow(type);
    });
  });

  // Custom stages checkboxes (only when custom workflow selected)
  customStageCheckboxes.forEach((cb) => {
    cb.addEventListener("change", () => {
      const selectedWorkflowType = document.querySelector(
        '.workflow-radio:checked'
      );
      if (selectedWorkflowType && selectedWorkflowType.value === "custom") {
        updateSummaryForWorkflow("custom");
      }
    });
  });

  // Deadline change → recompute timeline distribution
  if (deadlineInput) {
    deadlineInput.addEventListener("change", () => {
      const selectedWorkflowType =
        document.querySelector('.workflow-radio:checked')?.value || "long";
      updateSummaryForWorkflow(selectedWorkflowType);
    });
  }

  // Initial render for default "long" workflow on page load
  refreshSelectionVisual("long");
  updateSummaryForWorkflow("long");
});