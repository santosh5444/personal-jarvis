# Jarvis - Voice AI Assistant (Windows)

A voice AI assistant for Windows featuring local Whisper speech recognition, Groq ultra-fast LLM conversational intelligence, and native offline text-to-speech.

---

## ✨ Features
- **Wake Word Engine**: Local, real-time openWakeWord (`hey_jarvis` ONNX model) with zero cloud latency and low CPU usage.
- **Audio Chimes**: Instant dual-tone futuristic activation and sleep sounds via Windows native audio.
- **Speech-to-Text (STT)**: High-accuracy local `faster-whisper` (`base.en` with Silero VAD & Beam Search) with automatic Google Web Speech API fallback.
- **AI Intelligence**: Groq API integration (`llama-3.3-70b-versatile` / `llama-3.1-8b-instant`) with in-memory multi-turn session history.
- **Spoken Prompt Tuning**: Generates concise, natural 1–3 sentence responses formatted specifically for voice output.
- **Text-to-Speech (TTS)**: Instant, offline speech synthesis via Windows native SAPI5 (`pyttsx3`).

---

## 🔑 Configuration (.env)

1. Sign up / log in to [Groq Console](https://console.groq.com/keys).
2. Click **Create API Key** and copy your generated key (`gsk_...`).
3. In the project folder `d:\jarvis\`, copy `.env.example` to `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
4. Open `.env` and configure your settings:
   ```env
   GROQ_API_KEY=gsk_your_actual_key_here
   GROQ_MODEL=llama-3.3-70b-versatile
   WAKE_WORD_ENABLED=true
   WAKE_WORD_THRESHOLD=0.5
   ```

---

## 🛠️ Windows PowerShell Setup Guide

### 1. Navigate to Directory
```powershell
cd d:\jarvis
```

### 2. Activate Virtual Environment
```powershell
# If execution policy is restricted:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# Activate venv:
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

---

## 🚀 Running Jarvis

Start the assistant:
```powershell
python main.py
```

### Voice Controls:
- **Wake Jarvis**: Say *"Hey Jarvis"* to wake Jarvis from standby. A futuristic activation chime will play and Jarvis will acknowledge.
- **Speak normally**: Jarvis listens, transcribes with local Whisper, queries Groq for a concise answer, and speaks it aloud.
- **Multi-turn conversation**: Jarvis remains awake for follow-up questions during the active session.
- **Put to Standby**: Say *"sleep"*, *"go to sleep"*, or *"standby"* (or pause for 7 seconds of silence) to return to passive listening.
- **Exit session**: Say *"exit"*, *"quit"*, *"stop"*, or press `Ctrl+C` to terminate the application.

---

## 📂 Project Structure
```text
d:\jarvis\
│
├── main.py            # Main application (STT + Groq LLM + TTS + loop)
├── requirements.txt   # Dependencies (groq, python-dotenv, faster-whisper, pyttsx3, etc.)
├── .env.example       # Example environment variables template
├── .env               # Your private Groq API key (ignored in git)
├── .gitignore         # Ignores .env and venv
└── README.md          # Setup & execution guide
```
