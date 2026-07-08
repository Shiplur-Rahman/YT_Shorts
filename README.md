                                                                     ¥T_Shorts 
                                                                     

```
# YT Shorts Generator

YT Shorts Generator is a local FastAPI web app that turns long-form podcast or talking-head videos into ready-to-post vertical YouTube Shorts. Upload a video, and the app transcribes the audio, uses Claude to select the strongest short-form moments, detects the active speaker, crops the video to a 9:16 format, and renders downloadable MP4 clips with metadata.

## Features

- Upload long-form videos through a simple browser UI
- Transcribe speech with `faster-whisper`
- Use Claude to identify high-hook clip moments
- Automatically crop clips to vertical 1080x1920 format
- Focus on the active speaker using face tracking and mouth/lower-face motion
- Render clips with `ffmpeg`
- Download individual clips or all clips as a ZIP
- Saves transcript, metadata, and rendered clips per job

## Tech Stack

- Python 3.12
- FastAPI
- Uvicorn
- faster-whisper
- Anthropic Claude API
- OpenCV / YuNet face detection
- ffmpeg
- Vanilla HTML, CSS, and JavaScript frontend


## How It Works

1. The user uploads a video.
2. Audio is extracted with `ffmpeg`.
3. `faster-whisper` generates a timestamped transcript.
4. Claude analyzes the transcript and selects the best Shorts moments.
5. OpenCV detects faces and chooses the likely active speaker.
6. Each selected segment is cropped, scaled, and rendered as a vertical MP4.
7. The app displays clips, titles, descriptions, hashtags, and download links.

## Output

Each job stores:

- `transcript.json`
- `metadata.json`
- Rendered clips in `clips/`
- Downloadable ZIP of all clips and metadata

## Notes

This project is optimized for podcast-style videos, interviews, webinars, and talking-head content where the strongest short clips come from spoken moments.
```
