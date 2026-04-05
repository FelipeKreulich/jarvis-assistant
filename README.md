<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux&logoColor=white" />
  <img src="https://img.shields.io/badge/LLM-Groq%20%7C%20LLaMA%203.3-orange?logo=meta&logoColor=white" />
  <img src="https://img.shields.io/badge/TTS-Edge%20TTS-blueviolet?logo=microsoft&logoColor=white" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
</p>

<h1 align="center">Jarvis Assistant</h1>

<p align="center">
  AI voice assistant for Linux with an animated plasma orb interface.<br/>
  Talk to Jarvis using natural voice — it listens, thinks via Groq LLM, and responds with natural Edge TTS.<br/>
  Can open apps, run commands, and search the web.
</p>

---

## Demo

> Hold **Space**, speak, release — Jarvis processes your voice, thinks, and responds out loud while the orb reacts in real time.

## Features

- **Voice-first interface** — hold Space or click the orb to talk
- **Animated plasma orb** — HTML5 Canvas rendered in QWebEngine at 60fps with 5 reactive states
- **Natural TTS** — Microsoft Edge neural voices (pt-BR and en-US auto-detected)
- **Groq LLM** — fast inference with LLaMA 3.3 70B
- **System control** — open apps, run shell commands, search the web by voice
- **Bilingual** — understands and responds in Portuguese and English
- **Frameless UI** — dark, minimal, draggable and resizable window
- **Conversation memory** — multi-turn chat context within each session

## Orb States

| State | Visual | Trigger |
|-------|--------|---------|
| **Idle** | Slow breathing pulse, cool navy/blue tones | Default state |
| **Listening** | Reacts to mic amplitude, bright cyan, ripple waves | Space held / orb clicked |
| **Thinking** | Purple vortex swirl, spinning loading arcs | After recording stops |
| **Speaking** | Warm blue-white pulses, expanding halos | TTS audio playing |
| **Error** | Red/orange flash | On any failure |

All transitions are eased (ease-in-out) with smooth color palette morphing.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| GUI | PyQt6 (frameless, Wayland/X11) |
| Orb animation | QWebEngineView + HTML5 Canvas |
| LLM | Groq API — LLaMA 3.3 70B Versatile |
| Speech-to-Text | Google Speech Recognition |
| Text-to-Speech | Edge TTS (Microsoft Azure neural voices) |
| Audio I/O | PyAudio |
| Audio decode | FFmpeg |

## Installation

### 1. System dependencies

```bash
# Debian / Ubuntu / Kali
sudo apt install python3 python3-venv portaudio19-dev ffmpeg

# Arch Linux
sudo pacman -S python portaudio ffmpeg
```

### 2. Clone and setup

```bash
git clone git@github.com:FelipeKreulich/jarvis-assistant.git
cd jarvis-assistant

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. API Key

Get a free API key at [console.groq.com](https://console.groq.com):

```bash
export GROQ_API_KEY="gsk_your_key_here"
```

Or just run the app — it will prompt you on first launch and save to `~/.config/jarvis/config.json`.

## Usage

```bash
source venv/bin/activate
python main.py
```

### Controls

| Input | Action |
|-------|--------|
| **Hold Space** | Record voice |
| **Release Space** | Stop recording, send to AI |
| **Click orb** | Toggle recording |
| **Escape** | Quit |

### Voice commands (examples)

| You say | Jarvis does |
|---------|------------|
| "Open Firefox" | Launches Firefox |
| "Search Google for Python tutorials" | Opens browser with Google search |
| "What time is it?" | Runs `date` and speaks the result |
| "Open the file manager" | Launches Nautilus/Thunar |
| General questions | Answers conversationally |

## Project Structure

```
jarvis-assistant/
├── main.py           # Entry point — PyQt6 window, state machine, input handling
├── orb_widget.py     # Animated orb (QWebEngineView + HTML5 Canvas)
├── gemini_client.py  # Groq/LLaMA API wrapper with conversation history
├── audio.py          # Mic recording, Google STT, Edge TTS playback
├── config.py         # API key management (~/.config/jarvis/)
└── requirements.txt
```

## License

MIT
