import os
import sys
import time
import queue
import threading
import wave
from pathlib import Path

import assemblyai as aai
import sounddevice as sd
from dotenv import load_dotenv
from assemblyai.streaming.v3 import (
    RealTimeTranscriber,
    RealTimeTranscriberOptions,
    RealTimeParameters,
    RealTimeEvents,
)

load_dotenv()

API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
SAMPLE_RATE = 16000
CHANNELS = 1
AUDIO_DIR = Path("recordings")
AUDIO_DIR.mkdir(exist_ok=True)

if not API_KEY:
    raise RuntimeError("ASSEMBLYAI_API_KEY is missing from .env")


def transcribe_prerecorded():
    """Record microphone audio to WAV, then transcribe the saved file."""
    try:
        duration = float(input("Recording duration in seconds: "))
        if duration <= 0:
            print("Duration must be greater than zero.")
            return
    except ValueError:
        print("Enter a valid number.")
        return

    print(f"\nRecording for {duration:g} seconds. Speak now...")

    try:
        audio = sd.rec(
            int(duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
        )
        sd.wait()
    except Exception as exc:
        print(f"Microphone error: {exc}")
        return

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    audio_path = AUDIO_DIR / f"answer_{timestamp}.wav"

    # Save PCM audio as a standard WAV file.
    with wave.open(str(audio_path), "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(2)  # int16 = 2 bytes
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(audio.tobytes())

    print(f"Audio saved: {audio_path}")
    print("Transcribing with AssemblyAI...")

    try:
        config = aai.TranscriptionConfig(
            speech_models=["universal-3-5-pro", "universal-2"],
            language_code="en",
        )

        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(str("./recordings/audio.mp3"), config=config)

        if transcript.status == aai.TranscriptStatus.error:
            print(f"Transcription failed: {transcript.error}")
            return

        print("\n--- PRERECORDED TRANSCRIPT ---")
        print(transcript.text or "[No speech detected]")
        print("------------------------------")

    except Exception as exc:
        print(f"AssemblyAI error: {exc}")


def transcribe_realtime():
    """Stream microphone PCM to AssemblyAI and display transcript turns."""
    audio_queue = queue.Queue()
    stop_event = threading.Event()
    errors = []

    def on_turn(client, event):
        # Turn events may include interim or finalized text.
        if event.transcript:
            prefix = "FINAL" if event.end_of_turn else "LIVE"
            print(f"\r[{prefix}] {event.transcript}", flush=True)

    def on_error(client, error):
        errors.append(error)
        print(f"\nAssemblyAI streaming error: {error}")

    def audio_callback(indata, frames, time_info, status):
        if status:
            print(f"\nAudio status: {status}", file=sys.stderr)

        if not stop_event.is_set():
            audio_queue.put(bytes(indata))

    def audio_chunks():
        """Yield microphone PCM chunks until recording is stopped."""
        while not stop_event.is_set() or not audio_queue.empty():
            try:
                chunk = audio_queue.get(timeout=0.2)
                yield chunk
            except queue.Empty:
                continue

    client = RealTimeTranscriber(
        RealTimeTranscriberOptions(api_key=API_KEY)
    )

    client.on(RealTimeEvents.Turn, on_turn)
    client.on(RealTimeEvents.Error, on_error)

    try:
        client.connect(
            RealTimeParameters(
                sample_rate=SAMPLE_RATE,
                speech_model="universal-3-5-pro",
            )
        )

        print("\nConnected to AssemblyAI.")
        print("Speak into your microphone.")
        print("Press Enter to stop and finalize the transcript.\n")

        # Run the audio stream in a separate thread so Enter can stop it.
        stream_thread = threading.Thread(
            target=lambda: client.stream(audio_chunks()),
            daemon=True,
        )

        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=3200,
            callback=audio_callback,
        ):
            stream_thread.start()
            input()

        stop_event.set()
        stream_thread.join()

        if errors:
            print("\nStreaming finished with errors.")
        else:
            print("\nReal-time transcription finished.")

    except KeyboardInterrupt:
        print("\nStopping transcription...")
        stop_event.set()

    except Exception as exc:
        print(f"\nReal-time STT error: {exc}")
        stop_event.set()

    finally:
        stop_event.set()
        try:
            client.disconnect(terminate=True)
        except Exception as exc:
            print(f"Disconnect warning: {exc}")


def main():
    aai.settings.api_key = API_KEY

    print("\n=== AssemblyAI STT Test ===")
    print("1. Real-time microphone transcription")
    print("2. Record audio, then transcribe")
    print("0. Exit")

    choice = input("\nChoose mode: ").strip()

    if choice == "1":
        transcribe_realtime()
    elif choice == "2":
        transcribe_prerecorded()
    elif choice == "0":
        return
    else:
        print("Invalid option.")


if __name__ == "__main__":
    main()


# import assemblyai as aai
# from dotenv import load_dotenv
# import os

# load_dotenv()

# aai.settings.base_url = "https://api.assemblyai.com"
# aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

# audio_file = "./recordings/audio.mp3"

# config = aai.TranscriptionConfig(
#     speech_models=["universal-3-5-pro", "universal-2"],
#     language_detection=True,
#     speaker_labels=True,
# )

# transcript = aai.Transcriber().transcribe(audio_file, config=config)

# if transcript.status == aai.TranscriptStatus.error:
#     raise RuntimeError(f"Transcription failed: {transcript.error}")
# print(f"\nFull Transcript:\n\n{transcript.text}")