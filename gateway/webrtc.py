"""WebRTC session management — PeerConnection lifecycle and ICE config."""

import asyncio
import json
import logging
import os

import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer

from engine.adapter import create_generator
from engine.types import AudioChunk
from gateway.audio.pcm_ring_buffer import PCMRingBuffer
from gateway.audio.webrtc_audio_source import WebRTCAudioSource

FRAME_SAMPLES = 960  # 20ms at 48kHz
SAMPLE_RATE = 48000

log = logging.getLogger("webrtc")


def ice_servers_to_rtc(servers: list) -> list:
    """Convert ICE server dicts to RTCIceServer objects."""
    result = []
    for s in servers:
        urls = s.get("urls", s.get("url", ""))
        if isinstance(urls, str):
            urls = [urls]
        result.append(RTCIceServer(
            urls=urls,
            username=s.get("username", ""),
            credential=s.get("credential", ""),
        ))
    return result


class BufferedGenerator:
    """Reads PCM from a ring buffer in 20ms chunks.

    Same interface as SineWaveGenerator (next_chunk() → AudioChunk)
    so WebRTCAudioSource doesn't need to change.
    """

    def __init__(self, ring_buffer: PCMRingBuffer):
        self.ring_buffer = ring_buffer

    def next_chunk(self) -> AudioChunk:
        """Read one 20ms frame (960 samples = 1920 bytes) from the ring buffer."""
        pcm = self.ring_buffer.read(FRAME_SAMPLES * 2)  # 2 bytes per int16 sample
        return AudioChunk(samples=pcm, sample_rate=SAMPLE_RATE, channels=1)


class Session:
    """Manages one WebRTC peer connection and its audio track."""

    def __init__(self, ice_servers: list = None):
        rtc_servers = ice_servers_to_rtc(ice_servers or [])
        config = RTCConfiguration(iceServers=rtc_servers) if rtc_servers else RTCConfiguration()
        self._pc = RTCPeerConnection(configuration=config)
        self._audio_source = WebRTCAudioSource()
        self._generator = None

        # Ring buffer for TTS audio (5 seconds capacity at 48kHz mono 16-bit)
        self._ring_buffer = PCMRingBuffer(capacity=48000 * 2 * 5)
        self._tts_generator = BufferedGenerator(self._ring_buffer)

        # Mic recording state
        self._recording = False
        self._mic_frames: list[bytes] = []
        self._mic_track = None
        self._mic_recv_task: asyncio.Task | None = None

        # Log state changes
        @self._pc.on("connectionstatechange")
        async def on_conn_state():
            log.info("Connection state: %s", self._pc.connectionState)

        @self._pc.on("iceconnectionstatechange")
        async def on_ice_state():
            log.info("ICE connection state: %s", self._pc.iceConnectionState)

        @self._pc.on("icegatheringstatechange")
        async def on_ice_gather():
            log.info("ICE gathering state: %s", self._pc.iceGatheringState)

        @self._pc.on("track")
        async def on_track(track):
            if track.kind != "audio":
                return
            log.info("Received remote audio track from browser mic")
            self._mic_track = track
            self._mic_recv_task = asyncio.ensure_future(self._recv_mic_audio(track))

    async def handle_offer(self, sdp: str) -> str:
        """Process client SDP offer, return SDP answer.

        aiortc bundles all ICE candidates into the answer SDP
        automatically (no trickle ICE support).
        """
        # Add our audio track to the connection
        self._pc.addTrack(self._audio_source)

        # Set the remote offer
        offer = RTCSessionDescription(sdp=sdp, type="offer")
        await self._pc.setRemoteDescription(offer)

        # Create and set local answer
        answer = await self._pc.createAnswer()
        await self._pc.setLocalDescription(answer)

        log.info("SDP answer created")
        return self._pc.localDescription.sdp

    def start_audio(self, voice_id: str):
        """Start streaming audio for the given voice."""
        self._generator = create_generator(voice_id)
        self._audio_source.set_generator(self._generator)
        log.info("Audio started: %s", voice_id)

    def stop_audio(self):
        """Stop streaming audio (track sends silence)."""
        self._audio_source.clear_generator()
        self._generator = None
        log.info("Audio stopped")

    async def speak_text(self, text: str):
        """Run TTS on text and feed audio into the WebRTC track.

        Synthesis runs in a thread pool to avoid blocking the event loop.
        The buffered generator is attached so WebRTC reads from the ring buffer.
        """
        from engine.tts import synthesize

        # Ensure the TTS generator is attached to the audio source
        self._audio_source.set_generator(self._tts_generator)

        # Run TTS in a thread (CPU-bound ONNX inference)
        loop = asyncio.get_event_loop()
        pcm_48k = await loop.run_in_executor(None, synthesize, text)

        if pcm_48k:
            self._ring_buffer.write(pcm_48k)
            log.info("Wrote %d bytes of TTS audio to ring buffer", len(pcm_48k))

    async def _recv_mic_audio(self, track):
        """Background task: continuously receive audio frames from the browser mic track."""
        logged_format = False
        while True:
            try:
                frame = await track.recv()
            except Exception:
                log.info("Mic track ended")
                break

            if not logged_format:
                arr = frame.to_ndarray()
                log.info(
                    "Mic frame format=%s rate=%d samples=%d shape=%s dtype=%s range=[%s, %s]",
                    frame.format.name, frame.sample_rate, frame.samples,
                    arr.shape, arr.dtype, arr.min(), arr.max(),
                )
                logged_format = True

            if self._recording:
                arr = frame.to_ndarray()
                # Handle float formats (fltp/flt) — scale to int16
                if arr.dtype in (np.float32, np.float64):
                    arr = (arr * 32767).clip(-32768, 32767).astype(np.int16)
                # s16 interleaved stereo: shape=(1, samples*channels) — take every other sample for mono
                flat = arr.flatten()
                channels = flat.shape[0] // frame.samples
                if channels > 1:
                    flat = flat[::channels]  # take left channel
                pcm = flat.astype(np.int16).tobytes()
                self._mic_frames.append(pcm)

    def start_recording(self):
        """Start buffering incoming mic audio frames."""
        self._mic_frames.clear()
        self._recording = True
        log.info("Mic recording started")

    async def stop_recording(self) -> str:
        """Stop recording, concatenate frames, run STT, return text."""
        self._recording = False

        if not self._mic_frames:
            log.warning("No mic frames captured")
            return ""

        # Concatenate all buffered PCM frames
        pcm_data = b"".join(self._mic_frames)
        num_frames = len(self._mic_frames)
        self._mic_frames.clear()

        # Debug: check audio levels and save WAV
        samples = np.frombuffer(pcm_data, dtype=np.int16)
        log.info(
            "Mic recording stopped: %d frames, %d bytes, range=[%d, %d], rms=%.1f",
            num_frames, len(pcm_data), samples.min(), samples.max(),
            np.sqrt(np.mean(samples.astype(np.float64) ** 2)),
        )

        # Save debug WAV
        import wave
        from pathlib import Path
        wav_path = Path(__file__).resolve().parent.parent / "logs" / "mic_debug.wav"
        wav_path.parent.mkdir(exist_ok=True)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_data)
        log.info("Saved mic debug WAV: %s", wav_path)

        # Run STT in thread pool (CPU-bound Whisper inference)
        from engine.stt import transcribe
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, transcribe, pcm_data, SAMPLE_RATE)
        return text

    async def close(self):
        """Tear down the peer connection."""
        self.stop_audio()
        self._recording = False
        if self._mic_recv_task:
            self._mic_recv_task.cancel()
        await self._pc.close()
        log.info("Session closed")
