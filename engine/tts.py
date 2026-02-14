"""Piper TTS wrapper — text to 48kHz PCM with resampling."""

import logging
import os
import urllib.request
from pathlib import Path

import numpy as np
from scipy.signal import resample

log = logging.getLogger("tts")

TARGET_RATE = 48000  # WebRTC Opus expects 48kHz

# Model config
MODEL_NAME = "en_US-lessac-medium"
MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
MODEL_URL = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/{MODEL_NAME}.onnx"
CONFIG_URL = f"{MODEL_URL}.json"

# Lazy-loaded Piper voice
_voice = None


def _download_model():
    """Download the Piper ONNX model if not present."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    onnx_path = MODEL_DIR / f"{MODEL_NAME}.onnx"
    config_path = MODEL_DIR / f"{MODEL_NAME}.onnx.json"

    if not onnx_path.exists():
        log.info("Downloading voice model: %s (~60MB)...", MODEL_NAME)
        urllib.request.urlretrieve(MODEL_URL, onnx_path)
        log.info("Model downloaded: %s", onnx_path)

    if not config_path.exists():
        log.info("Downloading voice config...")
        urllib.request.urlretrieve(CONFIG_URL, config_path)
        log.info("Config downloaded: %s", config_path)

    return onnx_path


def _get_voice():
    """Load the Piper voice model on first use."""
    global _voice
    if _voice is not None:
        return _voice

    from piper import PiperVoice

    model_path = _download_model()
    log.info("Loading Piper TTS voice: %s", model_path)
    _voice = PiperVoice.load(str(model_path))
    log.info("Piper voice loaded (native rate: %d Hz)", _voice.config.sample_rate)
    return _voice


def synthesize(text: str) -> bytes:
    """Convert text to 48kHz mono int16 PCM bytes.

    Pipeline: text → Piper TTS (22050Hz chunks) → concat → resample → 48kHz PCM
    """
    voice = _get_voice()
    native_rate = voice.config.sample_rate  # typically 22050

    # Synthesize — yields AudioChunk objects
    raw_parts = []
    for chunk in voice.synthesize(text):
        raw_parts.append(chunk.audio_int16_bytes)

    if not raw_parts:
        log.warning("TTS produced no audio for: %r", text[:50])
        return b""

    raw_pcm = b"".join(raw_parts)

    # Convert to numpy for resampling
    samples = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float64)
    num_output_samples = int(len(samples) * TARGET_RATE / native_rate)

    # Resample from native rate to 48kHz
    resampled = resample(samples, num_output_samples)

    # Clip and convert back to int16
    resampled = np.clip(resampled, -32768, 32767).astype(np.int16)

    log.info(
        "TTS: %d chars → %d samples @ %dHz → %d samples @ %dHz (%.2fs)",
        len(text),
        len(samples),
        native_rate,
        len(resampled),
        TARGET_RATE,
        len(resampled) / TARGET_RATE,
    )
    return resampled.tobytes()
