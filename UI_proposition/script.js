
// RFQ lifecycle unified table logic
document.addEventListener("DOMContentLoaded", () => {
  const stepsBody = document.getElementById("steps-body");
  if (!stepsBody) return; // run only on this page

  const workflowRadios = document.querySelectorAll('input[name="workflowType"].workflow-radio');
  const customStageCheckboxes = document.querySelectorAll(".custom-stage");
  const toggleOptional = document.getElementById("toggle-optional");
  const deadlineInput = document.getElementById("deadline");

  const teams = [
    "Sales / BD",
    "Engineering",
    "Estimation",
    "Procurement",
    "Management",
    "Finance"
  ];

  const allLongStages = [
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
    "Award / Lost"
  ];

  const allShortStages = [
    "RFQ received",
    "Cost estimation",
    "Internal approval",
    "Offer submission",
    "Award / Lost"
  ];

  const stageType = {
    "RFQ received": "Mandatory",
    "Go / No-Go": "Mandatory",
    "Pre-bid clarifications": "Optional",
    "Preliminary design": "Mandatory",
    "BOQ / BOM preparation": "Mandatory",
    "Vendor inquiry": "Optional",
    "Cost estimation": "Mandatory",
    "Internal approval": "Mandatory",
    "Offer submission": "Mandatory",
    "Post-bid clarifications": "Optional",
    "Award / Lost": "Mandatory"
  };

  const stageTeamDefault = {
    "RFQ received": "Sales / BD",
    "Go / No-Go": "Management",
    "Pre-bid clarifications": "Sales / BD",
    "Preliminary design": "Engineering",
    "BOQ / BOM preparation": "Engineering",
    "Vendor inquiry": "Procurement",
    "Cost estimation": "Estimation",
    "Internal approval": "Management",
    "Offer submission": "Sales / BD",
    "Post-bid clarifications": "Sales / BD",
    "Award / Lost": "Management"
  };

  const stageDaysDefault = {
    "RFQ received": 0,
    "Go / No-Go": 2,
    "Pre-bid clarifications": 3,
    "Preliminary design": 5,
    "BOQ / BOM preparation": 4,
    "Vendor inquiry": 5,
    "Cost estimation": 4,
    "Internal approval": 2,
    "Offer submission": 1,
    "Post-bid clarifications": 4,
    "Award / Lost": 0
  };

  function getWorkflowType() {
    const r = document.querySelector('input[name="workflowType"].workflow-radio:checked');
    return r ? r.value : "long";
  }

  function getStagesForWorkflow(type) {
    if (type === "short") return allShortStages.slice();
    if (type === "custom") {
      const selected = [];
      customStageCheckboxes.forEach(cb => {
        if (cb.checked) selected.push(cb.value);
      });
      // Always keep order of declaration in the HTML (checkbox order)
      return selected;
    }
    return allLongStages.slice(); // default long
  }

  function getTodayAtMidnight() {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }

  function parseDeadline() {
    if (!deadlineInput || !deadlineInput.value) return null;
    const d = new Date(deadlineInput.value);
    if (Number.isNaN(d.getTime())) return null;
    d.setHours(0, 0, 0, 0);
    return d;
  }

  function formatISO(d) {
    if (!(d instanceof Date) || Number.isNaN(d.getTime())) return "";
    return d.toISOString().slice(0, 10);
  }

  function renderTable() {
    const showOptional = toggleOptional ? toggleOptional.checked : true;
    const workflowType = getWorkflowType();
    const baseStages = getStagesForWorkflow(workflowType);

    // Filter optional stages if toggle is off
    const stages = baseStages.filter(stageName => {
      if (showOptional) return true;
      return (stageType[stageName] || "Mandatory") !== "Optional";
    });

    stepsBody.innerHTML = "";

    if (!stages.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 7;
      td.textContent = "No stages selected for this workflow.";
      tr.appendChild(td);
      stepsBody.appendChild(tr);
      return;
    }

    const startDate = getTodayAtMidnight();
    let deadlineDate = parseDeadline();

    if (!deadlineDate) {
      // Fallback: one day per stage
      deadlineDate = new Date(startDate.getTime());
      deadlineDate.setDate(deadlineDate.getDate() + stages.length);
    }

    const msPerDay = 1000 * 60 * 60 * 24;
    const rawDiffDays = (deadlineDate - startDate) / msPerDay;
    const totalDays = Math.max(rawDiffDays, stages.length); // at least 1 day per stage
    const segment = totalDays / stages.length;

    stages.forEach((stageName, index) => {
      const tr = document.createElement("tr");

      // Index
      let tdIndex = document.createElement("td");
      tdIndex.textContent = String(index + 1);
      tr.appendChild(tdIndex);

      // Stage
      let tdStage = document.createElement("td");
      tdStage.textContent = stageName;
      tr.appendChild(tdStage);

      // Type
      let tdType = document.createElement("td");
      tdType.textContent = stageType[stageName] || "Mandatory";
      tr.appendChild(tdType);

      // Assigned team (select)
      let tdTeam = document.createElement("td");
      const sel = document.createElement("select");
      sel.className = "field-input";
      teams.forEach(team => {
        const opt = document.createElement("option");
        opt.value = team;
        opt.textContent = team;
        if (team === (stageTeamDefault[stageName] || teams[0])) {
          opt.selected = true;
        }
        sel.appendChild(opt);
      });
      tdTeam.appendChild(sel);
      tr.appendChild(tdTeam);

      // Creator can change team (checkbox)
      let tdChange = document.createElement("td");
      const chk = document.createElement("input");
      chk.type = "checkbox";
      chk.checked = true;
      tdChange.appendChild(chk);
      tr.appendChild(tdChange);

      // Target duration (days)
      let tdDays = document.createElement("td");
      const inp = document.createElement("input");
      inp.type = "number";
      inp.min = "0";
      inp.value = stageDaysDefault[stageName] != null ? stageDaysDefault[stageName] : 0;
      inp.className = "field-input";
      inp.style.maxWidth = "90px";
      tdDays.appendChild(inp);
      tr.appendChild(tdDays);

      // Planned (start → end)
      let tdPlanned = document.createElement("td");
      const segStart = new Date(startDate.getTime());
      segStart.setDate(segStart.getDate() + Math.floor(segment * index));
      const segEnd = new Date(startDate.getTime());
      segEnd.setDate(segEnd.getDate() + Math.floor(segment * (index + 1)));

      tdPlanned.textContent = formatISO(segStart) + " → " + formatISO(segEnd);
      tr.appendChild(tdPlanned);

      stepsBody.appendChild(tr);
    });
  }

  // Event listeners
  workflowRadios.forEach(radio => {
    radio.addEventListener("change", renderTable);
  });

  customStageCheckboxes.forEach(cb => {
    cb.addEventListener("change", () => {
      if (getWorkflowType() === "custom") {
        renderTable();
      }
    });
  });

  if (toggleOptional) {
    toggleOptional.addEventListener("change", renderTable);
  }

  if (deadlineInput) {
    deadlineInput.addEventListener("change", renderTable);
  }

  // Initial render
  renderTable();
});
