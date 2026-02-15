"""Faster-Whisper STT wrapper — audio bytes to text."""

import logging

import numpy as np
from scipy.signal import resample

log = logging.getLogger("stt")

MODEL_SIZE = "base"  # ~75MB, good accuracy for short utterances

# Lazy-loaded Whisper model
_model = None


def _get_model():
    """Load the faster-whisper model on first use (auto-downloads)."""
    global _model
    if _model is not None:
        return _model

    from faster_whisper import WhisperModel

    log.info("Loading faster-whisper model: %s (first run downloads ~75MB)...", MODEL_SIZE)
    _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    log.info("Whisper model loaded: %s", MODEL_SIZE)
    return _model


def transcribe(audio_bytes: bytes, sample_rate: int = 48000) -> str:
    """Transcribe PCM int16 audio bytes to text.

    Args:
        audio_bytes: Raw PCM int16 mono audio bytes.
        sample_rate: Sample rate of the audio (default 48kHz from WebRTC).

    Returns:
        Transcribed text string, or empty string if nothing detected.
    """
    if not audio_bytes:
        return ""

    model = _get_model()

    # Convert int16 PCM to float32 normalized [-1.0, 1.0] — what faster-whisper expects
    samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    duration = len(samples) / sample_rate
    log.debug("Transcribing %.2fs of audio (%d samples @ %dHz)", duration, len(samples), sample_rate)

    # Resample to 16kHz — faster-whisper expects 16kHz input
    WHISPER_RATE = 16000
    if sample_rate != WHISPER_RATE:
        num_output = int(len(samples) * WHISPER_RATE / sample_rate)
        samples = resample(samples, num_output).astype(np.float32)
        log.debug("Resampled to %d samples @ %dHz", len(samples), WHISPER_RATE)

    segments, info = model.transcribe(samples, beam_size=5, language="en")

    # Collect all segment texts
    text_parts = []
    for segment in segments:
        text_parts.append(segment.text.strip())

    result = " ".join(text_parts).strip()
    log.info("Transcription: %r", result[:100])
    return result
