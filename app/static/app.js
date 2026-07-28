const form = document.querySelector("#generator");
const status = document.querySelector("#status");
const result = document.querySelector("#result");
const comic = document.querySelector("#comic");
const download = document.querySelector("#download");
const manifest = document.querySelector("#manifest");
const button = form.querySelector("button");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  result.hidden = true;
  button.disabled = true;
  status.textContent = "Transcribing, choosing frames, drawing panels, and arranging tiny rectangles with unreasonable confidence…";

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

    const cacheBusted = `${data.comic_path}?v=${Date.now()}`;
    comic.src = cacheBusted;
    download.href = data.comic_path;
    manifest.textContent = JSON.stringify(data, null, 2);
    result.hidden = false;
    status.textContent = `Done. ${data.beats.length} panels selected.`;
    result.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    button.disabled = false;
  }
});
