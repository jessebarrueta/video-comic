# Video Comic MVP

A deliberately narrow local app that converts a spoken-performance clip plus a style reference into one or more comic pages.

## What it does

1. Extracts mono audio with FFmpeg.
2. Transcribes locally with Faster Whisper and word timestamps.
3. Groups words into timed narrative beats.
4. Uses OpenRouter structured output to choose and rank the beats.
   - If no OpenRouter key is configured, deterministic heuristics take over.
5. Extracts multiple candidate frames for each selected beat and scores them locally.
6. Prefers frames that are sharper, better exposed, and more likely to read clearly in a panel.
7. Sends the chosen frame plus the style reference to OpenAI's image-edit endpoint.
8. Builds deterministic comic pages locally with face-aware cropping and bubble-aware placement.
9. Lets you manually regenerate a single panel, optionally refining its art direction or lettering.

The image model never renders the lettering. This is intentional; exact text is software's job, not a probabilistic art goblin's.

## Current scope

- Best with monologues, stand-up, and short conversational clips.
- Hard limit defaults to 300 seconds.
- Supports multi-page output.
- Up to 6 panels per page and 18 total selected panels by default.
- No speaker diarization yet.
- Every panel is stylized independently, so visual continuity can vary.

## Upgrades in this build

- **Face-aware bubble placement**: bubble placement now penalizes overlap with detected faces.
- **Face-aware crops**: panel fitting tries to keep the largest detected face present and readable.
- **Manual panel regeneration**: the UI exposes per-panel regenerate controls with optional extra art direction and lettering edits.
- **Multi-page output**: longer clips can spill into multiple comic pages instead of being crammed into one.

## Requirements

- Python 3.11+
- FFmpeg and ffprobe
- An OpenAI API key for stylization, unless `SKIP_STYLIZATION=true`
- An optional OpenRouter API key for editorial beat selection

### macOS setup

```bash
brew install ffmpeg
cd video-comic-mvp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest  # optional, for the test suite
cp .env.example .env
```

Edit `.env` and add:

```dotenv
OPENAI_API_KEY=your-key
OPENROUTER_API_KEY=your-key
```

The OpenRouter key is optional. The OpenAI key is required unless you first test with:

```dotenv
SKIP_STYLIZATION=true
```

Run:

```bash
./run.sh
```

Then open `http://127.0.0.1:8000`.

## First-run behavior

Faster Whisper downloads the configured transcription model the first time it runs. The default is `small`; use `base` for a lighter download or `medium` for better transcription.

For Apple Silicon, the safest initial configuration is:

```dotenv
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

## Debug mode

Start with:

```dotenv
SKIP_STYLIZATION=true
OPENROUTER_API_KEY=
```

That tests upload, FFmpeg, transcription, beat grouping, frame extraction, frame scoring, page layout, and speech bubbles without paid calls.

Generated jobs live in `var/jobs/<job-id>/` and include:

- source video and style reference
- extracted WAV
- selected source frames
- candidate frames under `frame-candidates/`
- generated panel images
- generated page images under `pages/`
- `manifest.json`
- word-level `transcript.json`
- `openrouter-error.txt` when the editorial request fails and heuristics take over

## Chrome DevTools automatic workspace

The project includes and serves:

```text
/.well-known/appspecific/com.chrome.devtools.json
```

When the FastAPI server starts, it refreshes the file with the current absolute project root while retaining a stable UUID. The endpoint is served only for `localhost`, `127.0.0.1`, or `::1`, since the descriptor contains a local filesystem path.

## API

### `POST /api/generate`

Multipart fields:

- `video`
- `style_reference`

Returns the transcript, selected beats, generated pages, and per-panel metadata.

### `GET /api/jobs/{job_id}`

Returns a previously generated job manifest.

### `POST /api/jobs/{job_id}/panels/{panel_index}/regenerate`

JSON body:

```json
{
  "bubble_text": "Optional updated lettering",
  "prompt_suffix": "Optional extra art direction"
}
```

Re-stylizes a single panel and re-composes the affected pages.

### `GET /api/health`

Shows whether OpenRouter, OpenAI, and stylization are configured.

## Tests

```bash
pytest
```

## macOS native-library warning / Python version

Use Python **3.11, 3.12, or 3.13** for this project. Python 3.12 is the recommended boring option.

OpenCV and Faster Whisper's PyAV dependency both bundle FFmpeg libraries. Earlier builds loaded both into the FastAPI process on macOS, which could produce duplicate `AVFFrameReceiver` / `AVFAudioReceiver` Objective-C class warnings and unstable crashes. Face detection now runs in an isolated worker process so OpenCV and PyAV do not share the same native address space.

Recreate an existing Python 3.14 environment with Python 3.12:

```bash
deactivate 2>/dev/null || true
rm -rf .venv
brew install python@3.12
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
cp -n .env.example .env
./run.sh
```

The default transcription settings are now CPU + INT8:

```dotenv
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

This avoids the harmless but noisy warning about converting float16 model weights to float32 on a CPU backend.
