"""
Voice AI Assistant (Windows) - Jarvis with Wake Word & Groq LLM
========================================================================
Features:
- Wake Word: Local, offline openWakeWord ('Hey Jarvis' ONNX model) with zero cloud latency
- Speech-to-Text: High-accuracy local Whisper (`base.en` + Silero VAD + Beam Search) with Google API fallback
- Conversational Intelligence: Groq API with auto model discovery (`llama-3.3-70b-versatile`, `qwen/qwen3.6-27b`, etc.)
- In-memory multi-turn session dialog history
- Text-to-Speech: Offline Windows SAPI5 via pyttsx3
- Audio feedback: Futuristic activation chimes via winsound
- Standby / Sleep mode: Automatic timeout after silence or explicit voice commands ("sleep", "standby")
"""

import os
import sys
import io
import time
import re
import random
import numpy as np
import speech_recognition as sr
from dotenv import load_dotenv

# Ensure console supports UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# Terminal Styling
# ---------------------------------------------------------------------------
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    COLOR_INFO = Fore.CYAN
    COLOR_USER = Fore.GREEN + Style.BRIGHT
    COLOR_BOT = Fore.YELLOW + Style.BRIGHT
    COLOR_ALERT = Fore.RED + Style.BRIGHT
    COLOR_DIM = Fore.LIGHTBLACK_EX
except ImportError:
    COLOR_INFO = COLOR_USER = COLOR_BOT = COLOR_ALERT = COLOR_DIM = ""

# ---------------------------------------------------------------------------
# Audio Chimes & Sound Feedback
# ---------------------------------------------------------------------------
def play_wake_chime():
    """Plays an instant futuristic audio chime on wake detection."""
    try:
        import winsound
        winsound.Beep(880, 70)
        winsound.Beep(1320, 110)
    except Exception:
        pass

def play_sleep_chime():
    """Plays a descending tone when returning to standby mode."""
    try:
        import winsound
        winsound.Beep(1200, 70)
        winsound.Beep(700, 100)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 0. Wake Word Engine (openWakeWord - 'Hey Jarvis')
# ---------------------------------------------------------------------------
wakeword_model = None
wake_word_enabled = os.getenv("WAKE_WORD_ENABLED", "true").lower() in ("true", "1", "yes")
wake_word_threshold = float(os.getenv("WAKE_WORD_THRESHOLD", "0.30"))

def check_single_instance(port: int = 49231):
    """Ensures only one instance of Jarvis runs at a time to prevent audio device lock."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return s
    except socket.error:
        return None

def init_wakeword():
    """Initializes local openWakeWord model for 'Hey Jarvis' detection."""
    global wakeword_model
    if not wake_word_enabled:
        print(f"{COLOR_DIM}[WakeWord] Wake word detection disabled by configuration.")
        return False
        
    try:
        import openwakeword
        from openwakeword.model import Model
        print(f"{COLOR_INFO}[WakeWord] Initializing 'Hey Jarvis' wake word model (ONNX)...")
        wakeword_model = Model(wakeword_models=['hey_jarvis'], inference_framework='onnx')
        print(f"{COLOR_INFO}[WakeWord] Wake word engine ready (Sensitivity threshold: {wake_word_threshold}).")
        return True
    except Exception as e:
        print(f"{COLOR_ALERT}[WakeWord Error] Could not initialize wake word model: {e}")
        wakeword_model = None
        return False

def listen_for_wake_word(sample_rate: int = 16000) -> bool:
    """Listens continuously for 'Hey Jarvis' wake phrase using low-CPU streaming chunks."""
    global wakeword_model
    if wakeword_model is None:
        return True
        
    import sounddevice as sd
    chunk_samples = 1280  # 80ms chunk required by openWakeWord
    
    print(f"\n{COLOR_DIM}[Standby] Listening for 'Hey Jarvis' (Threshold: {wake_word_threshold:.2f})...")
    wakeword_model.reset()
    
    try:
        with sd.InputStream(samplerate=sample_rate, channels=1, dtype='int16') as stream:
            while True:
                data, _ = stream.read(chunk_samples)
                audio_frame = data.flatten()
                
                # Check live audio volume
                rms = np.sqrt(np.mean(audio_frame.astype(np.float32)**2))
                predictions = wakeword_model.predict(audio_frame)
                score = float(predictions.get('hey_jarvis', 0.0))
                
                if score >= wake_word_threshold:
                    print(f"\n{COLOR_BOT}[Wake Word Triggered!] Confidence: {score:.2f}")
                    wakeword_model.reset()
                    return True
                elif score >= 0.10 or rms > 150:
                    bar_len = int(min(score / wake_word_threshold, 1.0) * 10)
                    meter = "#" * bar_len + "-" * (10 - bar_len)
                    print(f"\r{COLOR_DIM}[Voice detected: [{meter}] Score: {score:.2f}/{wake_word_threshold:.2f}]", end="", flush=True)
    except Exception as e:
        print(f"{COLOR_ALERT}[WakeWord Stream Error] {e}")
        return True

# ---------------------------------------------------------------------------
# 1. Text-to-Speech (TTS) Engine (Windows Native SAPI.SpVoice + pyttsx3 Fallback)
# ---------------------------------------------------------------------------
sapi_voice = None
tts_engine = None

def init_tts():
    """Initializes Windows native SAPI.SpVoice offline TTS, with pyttsx3 fallback."""
    global sapi_voice, tts_engine
    
    # 1. Primary: Windows Direct SAPI.SpVoice via COM (bulletproof on Windows)
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        sapi_voice = win32com.client.Dispatch("SAPI.SpVoice")
        sapi_voice.Rate = 1       # -10 to +10 (1 is smooth natural speed)
        sapi_voice.Volume = 100   # Maximum volume (0 to 100)
        print(f"{COLOR_INFO}[TTS] Windows native SAPI.SpVoice initialized (Volume: 100%).")
        return True
    except Exception as e:
        print(f"{COLOR_DIM}[TTS Notice] Direct SAPI.SpVoice initialization failed: {e}. Trying pyttsx3...")
        sapi_voice = None

    # 2. Secondary: pyttsx3
    try:
        import pyttsx3
        tts_engine = pyttsx3.init(driverName='sapi5' if sys.platform == 'win32' else None)
        tts_engine.setProperty('rate', 180)
        tts_engine.setProperty('volume', 1.0)
        voices = tts_engine.getProperty('voices')
        if voices:
            tts_engine.setProperty('voice', voices[0].id)
        print(f"{COLOR_INFO}[TTS] pyttsx3 engine initialized.")
        return True
    except Exception as e:
        print(f"{COLOR_ALERT}[TTS Error] Could not initialize pyttsx3: {e}")
        tts_engine = None
        return False

def clean_for_speech(text: str) -> str:
    """Strips thinking tags, markdown, and special characters for natural voice output."""
    # Remove <think>...</think> reasoning blocks
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Remove markdown asterisks, hashes, backticks
    text = re.sub(r'[*_#`~]', '', text)
    # Replace non-ascii quotes/hyphens
    text = text.replace('’', "'").replace('“', '"').replace('”', '"').replace('—', '-').replace('–', '-')
    return text.strip()

def speak(text: str):
    """Speaks aloud the provided text string using offline Windows TTS."""
    spoken_text = clean_for_speech(text)
    if not spoken_text:
        return
    print(f"{COLOR_BOT}[Assistant] {spoken_text}")
    
    # 1. Primary: Windows Direct SAPI SpVoice
    if sapi_voice is not None:
        try:
            import pythoncom
            pythoncom.CoInitialize()
            sapi_voice.Speak(spoken_text)
            return
        except Exception as e:
            print(f"{COLOR_DIM}[TTS Notice] SAPI voice error ({e}). Trying pyttsx3...")

    # 2. Fallback: pyttsx3
    if tts_engine is not None:
        try:
            tts_engine.say(spoken_text)
            tts_engine.runAndWait()
        except Exception as e:
            print(f"{COLOR_ALERT}[TTS Error] Playback error: {e}")

# ---------------------------------------------------------------------------
# 2. Speech-to-Text (STT) Engine (High-Accuracy Whisper + Google Fallback)
# ---------------------------------------------------------------------------
whisper_model = None
stt_engine_name = "None"
WHISPER_MODEL_NAME = "base.en"

def init_stt():
    """Attempts to initialize local faster-whisper model; falls back to Google Speech API."""
    global whisper_model, stt_engine_name
    
    # 1. Attempt faster-whisper with base.en model
    try:
        from faster_whisper import WhisperModel
        print(f"{COLOR_INFO}[STT] Loading faster-whisper '{WHISPER_MODEL_NAME}' model (int8, CPU)...")
        whisper_model = WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type="int8")
        stt_engine_name = f"faster-whisper (local {WHISPER_MODEL_NAME} + Silero VAD)"
        print(f"{COLOR_INFO}[STT] High-accuracy Whisper model loaded successfully.")
        return
    except Exception as e:
        print(f"{COLOR_DIM}[STT Notice] faster-whisper {WHISPER_MODEL_NAME} failed ({e}). Trying tiny.en...")

    # Fallback to tiny.en
    try:
        from faster_whisper import WhisperModel
        whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        stt_engine_name = "faster-whisper (local tiny.en)"
        print(f"{COLOR_INFO}[STT] faster-whisper tiny.en loaded.")
        return
    except Exception:
        pass

    # 2. Fallback to Google Web Speech API
    whisper_model = None
    stt_engine_name = "Google Speech Recognition (Cloud Fallback)"
    print(f"{COLOR_INFO}[STT] Using SpeechRecognition with Google Web Speech API.")

def transcribe_audio(recognizer: sr.Recognizer, audio_data: sr.AudioData) -> str:
    """Transcribes audio using beam search, Silero VAD, and prompt guidance."""
    global whisper_model
    
    # 1. Local Whisper
    if whisper_model is not None:
        try:
            wav_bytes = audio_data.get_wav_data()
            audio_stream = io.BytesIO(wav_bytes)
            
            segments, info = whisper_model.transcribe(
                audio_stream,
                language="en",
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
                condition_on_previous_text=False,
                initial_prompt="English voice assistant speech commands and questions.",
                temperature=0.0
            )
            
            text_parts = [seg.text.strip() for seg in segments if seg.text.strip()]
            text = " ".join(text_parts).strip()
            if text:
                return text
        except Exception as e:
            print(f"{COLOR_DIM}[STT Whisper Notice] {e}. Trying Google Web Speech API...")

    # 2. Fallback to Google Web Speech API
    try:
        text = recognizer.recognize_google(audio_data)
        return text.strip()
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        print(f"{COLOR_ALERT}[STT Error] Google API request error: {e}")
        return ""

# ---------------------------------------------------------------------------
# 3. Audio Capture with Pre-Roll & Post-Roll Padding
# ---------------------------------------------------------------------------
def record_phrase(sample_rate: int = 16000, silence_timeout: float = 1.0, max_duration: float = 15.0, initial_timeout: float = 6.0) -> sr.AudioData:
    """Records speech from default microphone using sounddevice with initial timeout."""
    import sounddevice as sd
    
    chunk_duration = 0.05  # 50ms chunks
    chunk_samples = int(sample_rate * chunk_duration)
    
    pre_buffer_chunks = 6  # 300ms pre-roll
    post_silence_chunks = int(silence_timeout / chunk_duration)
    max_total_chunks = int(max_duration / chunk_duration)
    initial_timeout_chunks = int(initial_timeout / chunk_duration)
    
    pre_roll_ring = []
    recorded_speech_frames = []
    has_speech_started = False
    consecutive_silence_count = 0
    total_elapsed_chunks = 0
    
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype='int16') as stream:
        ambient_samples = []
        for _ in range(5):
            data, _ = stream.read(chunk_samples)
            rms = np.sqrt(np.mean(data.astype(np.float32)**2))
            ambient_samples.append(rms)
            
        ambient_baseline = max(np.mean(ambient_samples), 80)
        speech_threshold = max(ambient_baseline * 2.0, 250)
        
        print(f"{COLOR_INFO}[Mic] Listening... (Speak clearly)")
        
        for _ in range(max_total_chunks):
            data, _ = stream.read(chunk_samples)
            total_elapsed_chunks += 1
            rms = np.sqrt(np.mean(data.astype(np.float32)**2))
            
            if not has_speech_started:
                pre_roll_ring.append(data.tobytes())
                if len(pre_roll_ring) > pre_buffer_chunks:
                    pre_roll_ring.pop(0)
                
                if rms > speech_threshold:
                    has_speech_started = True
                    recorded_speech_frames.extend(pre_roll_ring)
                    consecutive_silence_count = 0
                elif total_elapsed_chunks > initial_timeout_chunks:
                    # User didn't speak within the initial timeout window
                    break
            else:
                recorded_speech_frames.append(data.tobytes())
                if rms < speech_threshold:
                    consecutive_silence_count += 1
                    if consecutive_silence_count > post_silence_chunks:
                        break
                else:
                    consecutive_silence_count = 0

    if not has_speech_started or len(recorded_speech_frames) == 0:
        return None

    raw_bytes = b"".join(recorded_speech_frames)
    return sr.AudioData(raw_bytes, sample_rate, 2)

# ---------------------------------------------------------------------------
# 4. Groq LLM Conversational Engine with Smart Model Discovery
# ---------------------------------------------------------------------------
groq_client = None
groq_model_name = "openai/gpt-oss-20b"

# Priority list of models to choose from if available in account
MODEL_CANDIDATES = [
    "openai/gpt-oss-20b",
    "groq/compound-mini",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-120b",
    "allam-2-7b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant"
]

SYSTEM_PROMPT = (
    "You are Jarvis, an intelligent, helpful, and concise voice assistant. "
    "Your responses will be spoken aloud to the user using text-to-speech. "
    "Keep your answers short, direct, and conversational (1 to 3 sentences maximum). "
    "Do not include thought chains, markdown formatting, bullet points, asterisks, URLs, or emojis."
)

conversation_history = [
    {"role": "system", "content": SYSTEM_PROMPT}
]

def init_groq():
    """Initializes the Groq client and automatically detects available models."""
    global groq_client, groq_model_name
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    
    if not api_key or api_key == "gsk_your_groq_api_key_here":
        print(f"{COLOR_ALERT}[LLM Warning] No valid GROQ_API_KEY found in .env file.")
        print(f"{COLOR_DIM}Please add your key to .env (see .env.example).")
        groq_client = None
        return False
        
    try:
        from groq import Groq
        groq_client = Groq(api_key=api_key)
        
        # Discover available models in user's Groq account
        try:
            available_models = [m.id for m in groq_client.models.list().data]
        except Exception:
            available_models = []
            
        configured_model = os.getenv("GROQ_MODEL", "").strip()
        
        if configured_model and (not available_models or configured_model in available_models):
            groq_model_name = configured_model
        else:
            # Pick first matching candidate available in user's account
            for candidate in MODEL_CANDIDATES:
                if candidate in available_models:
                    groq_model_name = candidate
                    break
            else:
                groq_model_name = available_models[0] if available_models else "openai/gpt-oss-20b"
                
        print(f"{COLOR_INFO}[LLM] Groq client connected successfully. Active Model: {groq_model_name}")
        return True
    except Exception as e:
        print(f"{COLOR_ALERT}[LLM Error] Failed to initialize Groq client: {e}")
        groq_client = None
        return False

def query_llm(user_message: str) -> str:
    """Sends user message to Groq chat completions with in-memory conversation history."""
    global groq_client, conversation_history, groq_model_name
    
    if groq_client is None:
        return "Please configure your Groq API key in the dot env file to enable AI responses."
        
    conversation_history.append({"role": "user", "content": user_message})
    
    # Keep dialog memory to last 10 turns
    if len(conversation_history) > 11:
        conversation_history = [conversation_history[0]] + conversation_history[-10:]
        
    try:
        completion = groq_client.chat.completions.create(
            model=groq_model_name,
            messages=conversation_history,
            temperature=0.6,
            max_tokens=150
        )
        
        raw_reply = completion.choices[0].message.content.strip()
        cleaned_reply = clean_for_speech(raw_reply)
        
        conversation_history.append({"role": "assistant", "content": cleaned_reply})
        return cleaned_reply
        
    except Exception as e:
        err_msg = str(e)
        print(f"{COLOR_ALERT}[LLM Error] {err_msg}")
        
        # Fallback to groq/compound-mini if current model encountered an error
        if groq_model_name != "groq/compound-mini":
            try:
                print(f"{COLOR_INFO}[LLM] Retrying with 'groq/compound-mini'...")
                completion = groq_client.chat.completions.create(
                    model="groq/compound-mini",
                    messages=conversation_history,
                    temperature=0.6,
                    max_tokens=150
                )
                raw_reply = completion.choices[0].message.content.strip()
                cleaned_reply = clean_for_speech(raw_reply)
                conversation_history.append({"role": "assistant", "content": cleaned_reply})
                groq_model_name = "groq/compound-mini"
                return cleaned_reply
            except Exception as retry_err:
                print(f"{COLOR_ALERT}[LLM Retry Error] {retry_err}")
                
        return "I am having trouble connecting to the AI service right now. Please try again in a moment."

# ---------------------------------------------------------------------------
# 5. Exit & Sleep Keyword Matching
# ---------------------------------------------------------------------------
def is_exit_command(text: str) -> bool:
    """Checks if the user requested to terminate the session completely."""
    clean = re.sub(r'[^\w\s]', '', text.lower()).strip()
    exit_triggers = {"exit", "quit", "stop", "goodbye", "bye", "shutdown", "close", "terminate"}
    words = clean.split()
    return clean in exit_triggers or any(w in exit_triggers for w in words[:2])

def is_sleep_command(text: str) -> bool:
    """Checks if the user requested to put Jarvis to sleep / standby mode."""
    clean = re.sub(r'[^\w\s]', '', text.lower()).strip()
    sleep_triggers = {"sleep", "go to sleep", "standby", "stand by", "rest", "sleep mode", "pause", "stop listening"}
    return clean in sleep_triggers or any(clean.startswith(t) for t in sleep_triggers)

# ---------------------------------------------------------------------------
# 6. Main Loop
# ---------------------------------------------------------------------------
def main():
    print("=" * 65)
    print(" Jarvis Voice Assistant - Wake Word & Groq Conversational AI")
    print("=" * 65)
    
    lock_socket = check_single_instance()
    if not lock_socket:
        print(f"\n{COLOR_ALERT}[Warning] Another instance of Jarvis is already running!")
        print(f"{COLOR_DIM}Please close any other Jarvis console window first.")
        time.sleep(4)
        return
        
    init_tts()
    init_stt()
    init_groq()
    has_wakeword = init_wakeword()
    
    print(f"{COLOR_INFO}[STT Engine]  {stt_engine_name}")
    print(f"{COLOR_INFO}[LLM Model]   {groq_model_name}")
    print(f"{COLOR_INFO}[Wake Word]   {'Hey Jarvis (openWakeWord ONNX)' if has_wakeword else 'Disabled'}")
    print(f"{COLOR_INFO}Commands: Say 'Hey Jarvis' to wake, 'sleep' to standby, 'exit' to quit.")
    print("=" * 65 + "\n")
    
    recognizer = sr.Recognizer()
    
    if has_wakeword:
        play_wake_chime()
        speak("Jarvis is online and standing by. Say Hey Jarvis to wake me up.")
    else:
        speak("Jarvis is online. How can I help you today?")
    
    try:
        while True:
            # 1. Passive Standby Mode (Wait for 'Hey Jarvis')
            if has_wakeword:
                listen_for_wake_word()
                play_wake_chime()
                
                # Conversational wake greeting
                wake_acknowledgments = ["Yes, sir?", "At your service.", "I'm listening.", "Online."]
                speak(random.choice(wake_acknowledgments))
            
            # 2. Active Conversational Session
            awake_session = True
            while awake_session:
                audio_data = record_phrase(initial_timeout=7.0)
                
                if audio_data is None:
                    if has_wakeword:
                        print(f"{COLOR_DIM}[Timeout] Silence detected. Returning to standby...")
                        play_sleep_chime()
                        awake_session = False
                        break
                    else:
                        continue
                        
                print(f"{COLOR_DIM}[Processing] Transcribing...")
                transcribed_text = transcribe_audio(recognizer, audio_data)
                
                if not transcribed_text:
                    if has_wakeword:
                        print(f"{COLOR_DIM}[No speech detected] Returning to standby...")
                        play_sleep_chime()
                        awake_session = False
                        break
                    else:
                        continue
                        
                print(f"{COLOR_USER}[You] \"{transcribed_text}\"")
                
                # Check for exit command
                if is_exit_command(transcribed_text):
                    speak("Goodbye! Have a great day.")
                    return
                    
                # Check for sleep command
                if is_sleep_command(transcribed_text):
                    play_sleep_chime()
                    speak("Standing by.")
                    awake_session = False
                    break
                    
                # Query Groq LLM
                print(f"{COLOR_DIM}[Thinking...]")
                ai_reply = query_llm(transcribed_text)
                
                # Speak response aloud
                speak(ai_reply)
                print()
                
                # If wake word is disabled, break to outer continuous loop
                if not has_wakeword:
                    break
                    
    except KeyboardInterrupt:
        print(f"\n{COLOR_INFO}\nInterrupted by user (Ctrl+C). Exiting...")
        speak("Session ended. Goodbye.")
    except Exception as e:
        print(f"{COLOR_ALERT}\n[Error] {e}")

if __name__ == "__main__":
    main()
