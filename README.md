# Voice I/O Prototype (Windows)

Stage 1 prototype proving voice-in (Speech-to-Text with local Whisper and Google Web Speech fallback) and voice-out (Text-to-Speech via offline Windows SAPI5 / `pyttsx3`).

---

## 🛠️ Windows Setup Guide (PowerShell)

### Step 1: Open PowerShell and Navigate to Project Directory
```powershell
cd d:\jarvis
```

### Step 2: Create and Activate Virtual Environment
```powershell
# Create virtual environment
python -m venv venv

# If PowerShell script execution is restricted, enable it for this session:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# Activate the virtual environment
.\venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```powershell
# Upgrade pip & wheel
python -m pip install --upgrade pip setuptools wheel

# Install required dependencies
pip install -r requirements.txt
```

#### 💡 Windows PyAudio Note:
On standard Python installations, `pip install PyAudio` installs the pre-compiled wheel directly.
If you encounter a `portaudio.h` build error, install `pipwin` or install the prebuilt wheel:
```powershell
pip install pipwin
pipwin install pyaudio
```

---

## 🚀 Running the Prototype

Run the single-file prototype with:
```powershell
python main.py
```

### What Happens on Startup:
1. **TTS Check**: Initializes offline Windows SAPI5 speech synthesis via `pyttsx3`.
2. **STT Engine Check**: 
   - Attempts to load local `faster-whisper` (`tiny.en` model, CPU `int8`).
   - If not installed or unsupported, it gracefully switches to `SpeechRecognition`'s Google Web Speech API fallback.
3. **Microphone Calibration**: Listens to 1 second of ambient room sound to set dynamic energy threshold.
4. **Interactive Loop**:
   - Listens to your microphone.
   - Prints the transcription: `👤 You said: "..."`
   - Responds via voice: `🤖 Assistant: I heard: ...`
   - Exits cleanly when you say *"exit"*, *"quit"*, *"stop"*, or press `Ctrl+C`.

---

## 📂 Project Structure
```text
d:\jarvis\
│
├── main.py            # Complete single-file Voice I/O prototype
├── requirements.txt   # Dependencies (pyttsx3, SpeechRecognition, PyAudio, etc.)
└── README.md          # Setup & execution instructions
```
