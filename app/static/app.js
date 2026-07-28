const form = document.querySelector("#generator");
const status = document.querySelector("#status");
const result = document.querySelector("#result");
const pages = document.querySelector("#pages");
const download = document.querySelector("#download");
const manifest = document.querySelector("#manifest");
const button = form.querySelector("button[type='submit']");
const panelControls = document.querySelector("#panel-controls");

let currentManifest = null;

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  result.hidden = true;
  button.disabled = true;
  status.textContent = "Transcribing, selecting frames, re-illustrating, and arguing with aesthetic probability fields…";

  const body = new FormData(form);

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      body,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Generation failed");
    }

    currentManifest = data;
    renderResult(data);
    status.textContent = `Done. ${data.panels.length} panels across ${data.page_count} page${data.page_count === 1 ? "" : "s"}. Style strength: ${data.style_strength}.`;
    result.hidden = false;
    result.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    button.disabled = false;
  }
});

function renderResult(data) {
  renderPages(data.comic_paths);
  renderPanelControls(data);
  download.href = data.comic_paths?.[0] || data.comic_path;
  download.textContent = data.page_count > 1 ? "Save first page" : "Save PNG";
  manifest.textContent = JSON.stringify(data, null, 2);
}

function renderPages(paths) {
  pages.innerHTML = "";
  (paths || []).forEach((path, index) => {
    const figure = document.createElement("figure");
    figure.className = "page";

    const caption = document.createElement("figcaption");
    caption.textContent = `Page ${index + 1}`;

    const img = document.createElement("img");
    img.alt = `Generated comic page ${index + 1}`;
    img.src = `${path}?v=${Date.now()}`;

    const link = document.createElement("a");
    link.href = path;
    link.download = `comic-page-${index + 1}.png`;
    link.textContent = "Download page";
    link.className = "download-inline";

    figure.append(caption, img, link);
    pages.appendChild(figure);
  });
}

function renderPanelControls(data) {
  panelControls.innerHTML = "";

  data.panels.forEach((panel) => {
    const card = document.createElement("div");
    card.className = "panel-card";

    const title = document.createElement("h3");
    title.textContent = `Panel ${panel.index + 1} · Page ${panel.page_index + 1}`;

    const thumb = document.createElement("img");
    thumb.src = `${panel.styled_frame}?v=${Date.now()}`;
    thumb.alt = `Styled panel ${panel.index + 1}`;
    thumb.className = "thumb";

    const bubble = document.createElement("textarea");
    bubble.value = panel.beat.bubble_text;
    bubble.rows = 3;
    bubble.placeholder = "Optional lettering edit";

    const prompt = document.createElement("textarea");
    prompt.rows = 2;
    prompt.placeholder = "Optional art direction for this panel (e.g. stronger grain, flatter shading, rougher linework)";

    const strengthLabel = document.createElement("label");
    strengthLabel.className = "mini stacked";
    strengthLabel.textContent = "Style strength";

    const strength = document.createElement("select");
    strength.innerHTML = `
      <option value="subtle">Subtle</option>
      <option value="balanced">Balanced</option>
      <option value="strong">Strong</option>
    `;
    strength.value = data.style_strength || "balanced";
    strengthLabel.appendChild(strength);

    const meta = document.createElement("p");
    meta.className = "mini";
    meta.textContent = `${panel.beat.kind} · importance ${panel.beat.importance}`;

    const row = document.createElement("div");
    row.className = "action-row";

    const refresh = document.createElement("button");
    refresh.type = "button";
    refresh.textContent = "Regenerate panel";

    const saveText = document.createElement("button");
    saveText.type = "button";
    saveText.className = "secondary";
    saveText.textContent = "Apply lettering edit";

    const state = document.createElement("span");
    state.className = "mini";

    refresh.addEventListener("click", async () => {
      await regeneratePanel(data.job_id, panel.index, {
        bubble_text: bubble.value,
        prompt_suffix: prompt.value,
        style_strength: strength.value,
      }, state, refresh, saveText);
    });

    saveText.addEventListener("click", async () => {
      await regeneratePanel(data.job_id, panel.index, {
        bubble_text: bubble.value,
        style_strength: strength.value,
      }, state, refresh, saveText);
    });

    row.append(refresh, saveText, state);
    card.append(title, thumb, meta, bubble, prompt, strengthLabel, row);
    panelControls.appendChild(card);
  });
}

async function regeneratePanel(jobId, panelIndex, body, state, ...buttons) {
  buttons.forEach((btn) => (btn.disabled = true));
  state.textContent = "Updating…";
  try {
    const response = await fetch(`/api/jobs/${jobId}/panels/${panelIndex}/regenerate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Panel regeneration failed");
    }
    currentManifest = data;
    renderResult(data);
    state.textContent = "Updated.";
  } catch (error) {
    state.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    buttons.forEach((btn) => (btn.disabled = false));
  }
}
