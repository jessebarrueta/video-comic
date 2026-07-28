# Video Comic MVP

A deliberately narrow local app that converts an uploaded performance clip—or a selected section of a YouTube video—plus a style reference into one or more comic pages.

## What it does

1. Accepts a local video upload or imports a user-selected YouTube section with yt-dlp.
2. Extracts mono audio with FFmpeg.
3. Transcribes locally with Faster Whisper and word timestamps.
4. Groups words into timed narrative beats.
5. Uses OpenRouter structured output to choose and rank the beats.
   - If no OpenRouter key is configured, deterministic heuristics take over.
6. Extracts multiple candidate frames for each selected beat and scores them locally.
7. Prefers frames that are sharper, better exposed, and more likely to read clearly in a panel.
8. Sends the chosen frame plus the style reference to OpenAI's image-edit endpoint.
9. Builds deterministic comic pages locally with optional face-aware cropping and bubble-aware placement.
10. Lets you manually regenerate a single panel, optionally refining its art direction or lettering.
11. Supports a style-strength control so the result can stay subtle or lean harder into the reference image.

The image model never renders the lettering. This is intentional; exact text is software's job, not a probabilistic art goblin's.

## Current scope

- Best with monologues, stand-up, and short conversational clips.
- YouTube import supports public YouTube/youtu.be links and requires explicit in/out times.
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
- **YouTube section import**: paste a link, enter in/out timestamps, and route the downloaded section through the existing pipeline.

## Requirements

- Python 3.11+
- FFmpeg and ffprobe
- An OpenAI API key for stylization, unless `SKIP_STYLIZATION=true`
- An optional OpenRouter API key for editorial beat selection
- `yt-dlp`, installed automatically by `requirements.txt`, for YouTube section import

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

- `source_type`: `upload` or `youtube`
- `video`: required when `source_type=upload`
- `youtube_url`: required when `source_type=youtube`
- `youtube_start`: seconds, `MM:SS`, or `HH:MM:SS`
- `youtube_end`: seconds, `MM:SS`, or `HH:MM:SS`
- `rights_confirmed`: must be true for YouTube imports
- `style_reference`
- `style_strength`: `subtle`, `balanced`, or `strong`

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

Shows whether OpenRouter, OpenAI, stylization, optional face detection, and YouTube importing are configured.

## Tests

```bash
pytest
```

## Style matching changes in this build

- The style prompt is now reference-driven instead of hardcoded to a generic comic look.
- The app explicitly tells the image model to imitate the specific visual language of the style reference.
- Balanced and strong modes no longer request high source-image fidelity, which gives the reference image more influence.
- Each stylized panel now saves the exact prompt used in a sidecar `.prompt.txt` file for debugging.

## Optional face detection

Face detection improves crop and speech-bubble placement, but it is no longer required for comic generation. The app will fall back to visual-activity scoring if OpenCV is absent or incomplete.

Install the optional detector with:

```bash
pip install -r requirements-face-detection.txt
```

Only one OpenCV wheel package should exist in a virtual environment because all OpenCV wheel variants share the same `cv2` import namespace. If `/api/health` reports an incomplete `cv2` module, clean the environment and reinstall only the headless package:

```bash
pip uninstall -y cv2 opencv-python opencv-contrib-python \
  opencv-python-headless opencv-contrib-python-headless
pip install -r requirements-face-detection.txt
```

The app remains usable without that optional reinstall; `face_detection.available` will simply be `false` in `/api/health`.

## Speech bubble placement changes in v2.5

- Long lines use wider, shallower balloons so they cover less of the speaker.
- Placement now considers visual activity, detected-face overlap, and tail distance together.
- Candidate positions include top-center and upper-side placements rather than only four corners.
- Tails attach to the nearest balloon edge and point toward the nearest face boundary.
- Tail width is capped, preventing the large triangular "speech spear" effect seen in earlier builds.


## YouTube section import

Choose **YouTube section** in the source selector, paste a public YouTube URL, and enter an in and out time. Accepted timestamp formats include:

```text
90
1:30
01:30.500
1:02:03
```

The app first inspects the video metadata, validates that the requested section is inside the video and under `MAX_VIDEO_SECONDS`, then invokes yt-dlp through the active virtual environment:

```text
<project>/.venv/bin/python -m yt_dlp
```

The resulting temporary clip is copied into the normal job directory before the upload workspace is deleted. YouTube import is intentionally limited to YouTube hosts, disables playlist downloading, and requires the user to confirm they own the video or have permission to use it.

If `/api/health` reports that YouTube importing is unavailable, update the active project environment:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```
