# Video Comic MVP

A deliberately narrow local app that converts a short spoken-performance clip plus a style reference into one comic page.

## What it does

1. Extracts mono audio with FFmpeg.
2. Transcribes locally with Faster Whisper and word timestamps.
3. Groups words into timed narrative beats.
4. Uses OpenRouter structured output to choose and rank up to six panels.
   - If no OpenRouter key is configured, deterministic heuristics take over.
5. Extracts multiple candidate frames for each selected beat and scores them locally.
6. Prefers frames that are sharper, better composed, and more likely to leave room for a speech bubble.
7. Sends the chosen frame plus the style reference to OpenAI's image-edit endpoint.
8. Builds a deterministic 1536×2048 comic page locally with bubble-aware placement and readable speech bubbles.

The image model never renders the lettering. This is intentional; exact text is software's job, not a probabilistic art goblin's.

## MVP constraints

- Best with 15–90 second monologues or stand-up clips.
- Hard limit defaults to 120 seconds.
- One page, up to six panels.
- No speaker diarization yet.
- Frame selection is quality-scored, but still lightweight rather than semantically omniscient.
- Every panel is stylized independently, so visual continuity can vary.

## Improvements in this build

- **Better frame selection**: each beat now samples several timestamps and chooses the best candidate using sharpness, face prominence, composition, and available bubble space.
- **Bubble-aware composition**: bubbles evaluate multiple candidate positions and try to avoid faces while seeking visually quieter regions.
- **Smaller typography under pressure**: long lines now shrink more aggressively before they engulf the entire panel like a bureaucratic memo.
- **Better crop behavior**: panels use face-aware centering when being fit into comic rectangles, which tends to reduce accidental emphasis on watermarks and platform furniture.
- **Debuggability**: each job saves `frame-selection.json` plus the candidate frames used in scoring.

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

CTranslate2 GPU support is platform-dependent, so make the boring path work before summoning the optimization demons.

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
- `comic.png`
- `manifest.json`
- word-level `transcript.json`
- frame scoring details in `frame-selection.json`
- `openrouter-error.txt` when the editorial request fails and heuristics take over

## API

### `POST /api/generate`

Multipart fields:

- `video`
- `style_reference`

Returns the transcript, selected beats, and final comic path.

### `GET /api/health`

Shows whether OpenRouter, OpenAI, and stylization are configured.

## Tests

```bash
pytest
```

## Likely next upgrades

The highest-value upgrades are speaker diarization, laughter detection, better visual expression scoring, and an editable intermediate panel plan. Resist the urge to implement all four in one caffeinated spiral.
