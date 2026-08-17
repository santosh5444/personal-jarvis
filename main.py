"""
Voice I/O Prototype (Windows) - High Accuracy Edition
=====================================================
Stage 1 (Enhanced):
- Upgraded Whisper model: `base.en` (higher accuracy, low latency)
- Silero VAD (Voice Activity Detection) filter enabled
- Beam Search decoding (beam_size=5) to prevent phonetic mismatches
- Pre-roll and post-roll audio padding to prevent clipped syllables
- Offline TTS via pyttsx3 (SAPI5)
- Automatic fallback to Google Web Speech API
"""

import sys
import io
import time
import re
import numpy as np
import speech_recognition as sr

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
# 1. Text-to-Speech (TTS) Engine (pyttsx3 / Windows SAPI5)
# ---------------------------------------------------------------------------
tts_engine = None

def init_tts():
    """Initializes the offline pyttsx3 Text-to-Speech engine."""
    global tts_engine
    try:
        import pyttsx3
        tts_engine = pyttsx3.init(driverName='sapi5' if sys.platform == 'win32' else None)
        tts_engine.setProperty('rate', 180)    # Speed (words per minute)
        tts_engine.setProperty('volume', 1.0)  # Volume (0.0 to 1.0)
        
        voices = tts_engine.getProperty('voices')
        if voices:
            tts_engine.setProperty('voice', voices[0].id)
            
        print(f"{COLOR_INFO}[TTS] pyttsx3 offline engine initialized.")
        return True
    except Exception as e:
        print(f"{COLOR_ALERT}[TTS Error] Could not initialize pyttsx3: {e}")
        tts_engine = None
        return False

def speak(text: str):
    """Speaks aloud the provided text string using offline TTS."""
    print(f"{COLOR_BOT}🤖 Assistant: {text}")
    if tts_engine:
        try:
            tts_engine.say(text)
            tts_engine.runAndWait()
        except Exception as e:
            print(f"{COLOR_ALERT}[TTS Error] Playback error: {e}")

# ---------------------------------------------------------------------------
# 2. Speech-to-Text (STT) Engine (High-Accuracy Whisper + Google Fallback)
# ---------------------------------------------------------------------------
whisper_model = None
stt_engine_name = "None"
WHISPER_MODEL_NAME = "base.en"  # Upgraded from tiny.en for significantly better word accuracy

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

    # Fallback to tiny.en if base.en failed
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
    """
    Transcribes audio using high-accuracy beam-search decoding, Silero VAD filtering,
    and prompt guidance to eliminate word mismatches.
    """
    global whisper_model
    
    # 1. Try local Whisper with accuracy enhancements
    if whisper_model is not None:
        try:
            wav_bytes = audio_data.get_wav_data()
            audio_stream = io.BytesIO(wav_bytes)
            
            # Transcription options to maximize accuracy and minimize hallucinations:
            # - beam_size=5: Evaluates top 5 hypotheses
            # - vad_filter=True: Removes non-speech sounds/noise
            # - condition_on_previous_text=False: Prevents error cascading
            # - initial_prompt: Biases vocabulary towards standard spoken English
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

    # 2. Fallback: Google Web Speech API
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
def record_phrase(sample_rate: int = 16000, silence_timeout: float = 1.0, max_duration: float = 15.0) -> sr.AudioData:
    """
    Records speech from the default microphone using sounddevice.
    Includes rolling pre-buffer (300ms) and post-roll trailing frames (400ms)
    to guarantee zero clipped syllables at the start and end of phrases.
    """
    import sounddevice as sd
    
    chunk_duration = 0.05  # 50ms chunks for responsive voice boundary tracking
    chunk_samples = int(sample_rate * chunk_duration)
    
    pre_buffer_chunks = 6  # 300ms pre-roll buffer
    post_silence_chunks = int(silence_timeout / chunk_duration)
    max_total_chunks = int(max_duration / chunk_duration)
    
    pre_roll_ring = []
    recorded_speech_frames = []
    has_speech_started = False
    consecutive_silence_count = 0
    
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype='int16') as stream:
        # Measure baseline ambient noise for 250ms
        ambient_samples = []
        for _ in range(5):
            data, _ = stream.read(chunk_samples)
            rms = np.sqrt(np.mean(data.astype(np.float32)**2))
            ambient_samples.append(rms)
            
        ambient_baseline = max(np.mean(ambient_samples), 80)
        speech_threshold = max(ambient_baseline * 2.0, 250)
        
        print(f"{COLOR_INFO}🎤 Listening... (Speak clearly into microphone)")
        
        for _ in range(max_total_chunks):
            data, _ = stream.read(chunk_samples)
            rms = np.sqrt(np.mean(data.astype(np.float32)**2))
            
            if not has_speech_started:
                # Fill rolling pre-buffer
                pre_roll_ring.append(data.tobytes())
                if len(pre_roll_ring) > pre_buffer_chunks:
                    pre_roll_ring.pop(0)
                
                # Check if speech began
                if rms > speech_threshold:
                    has_speech_started = True
                    recorded_speech_frames.extend(pre_roll_ring)
                    consecutive_silence_count = 0
            else:
                # Speech in progress
                recorded_speech_frames.append(data.tobytes())
                
                if rms < speech_threshold:
                    consecutive_silence_count += 1
                    if consecutive_silence_count > post_silence_chunks:
                        # End of speech detected
                        break
                else:
                    consecutive_silence_count = 0

    if not has_speech_started or len(recorded_speech_frames) == 0:
        return None

    raw_bytes = b"".join(recorded_speech_frames)
    return sr.AudioData(raw_bytes, sample_rate, 2)

# ---------------------------------------------------------------------------
# 4. Exit Keyword Matching Helper
# ---------------------------------------------------------------------------
def is_exit_command(text: str) -> bool:
    """Checks if the user requested to terminate the session."""
    clean = re.sub(r'[^\w\s]', '', text.lower()).strip()
    exit_triggers = {"exit", "quit", "stop", "goodbye", "bye", "shutdown", "close"}
    words = clean.split()
    return clean in exit_triggers or any(w in exit_triggers for w in words[:2])

# ---------------------------------------------------------------------------
# 5. Main Loop
# ---------------------------------------------------------------------------
def main():
    print("=" * 65)
    print(" Voice I/O Prototype (Windows) - High Accuracy Edition")
    print("=" * 65)
    
    init_tts()
    init_stt()
    
    print(f"{COLOR_INFO}[STT Engine] {stt_engine_name}")
    print(f"{COLOR_INFO}Commands: Say 'exit', 'quit', 'stop' or press Ctrl+C to terminate.")
    print("=" * 65 + "\n")
    
    recognizer = sr.Recognizer()
    speak("Voice prototype is active. Speak into your microphone.")
    
    try:
        while True:
            audio_data = record_phrase()
            
            if audio_data is None:
                continue
                
            print(f"{COLOR_DIM}⏳ Transcribing with precision...")
            transcribed_text = transcribe_audio(recognizer, audio_data)
            
            if not transcribed_text:
                continue
                
            print(f"{COLOR_USER}👤 You said: \"{transcribed_text}\"")
            
            # Check for exit command
            if is_exit_command(transcribed_text):
                speak("Goodbye! Shutting down voice prototype.")
                break
                
            # Confirmation echo
            speak(f"I heard: {transcribed_text}")
            print()
            
    except KeyboardInterrupt:
        print(f"\n{COLOR_INFO}\nInterrupted by user (Ctrl+C). Exiting...")
        speak("Session ended. Goodbye.")
    except Exception as e:
        print(f"{COLOR_ALERT}\n[Error] {e}")

if __name__ == "__main__":
    main()
