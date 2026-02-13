"""WebRTC session management — PeerConnection lifecycle and ICE config."""

import json
import logging
import os

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer

from engine.adapter import create_generator
from gateway.audio.webrtc_audio_source import WebRTCAudioSource

log = logging.getLogger("webrtc")


def parse_ice_servers() -> list:
    """Parse ICE_SERVERS_JSON env var into RTCIceServer objects."""
    raw = os.getenv("ICE_SERVERS_JSON", "[]")
    try:
        servers = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Invalid ICE_SERVERS_JSON, using empty list")
        return []

    result = []
    for s in servers:
        urls = s.get("urls", "")
        if isinstance(urls, str):
            urls = [urls]
        result.append(RTCIceServer(
            urls=urls,
            username=s.get("username", ""),
            credential=s.get("credential", ""),
        ))
    return result


class Session:
    """Manages one WebRTC peer connection and its audio track."""

    def __init__(self):
        ice_servers = parse_ice_servers()
        config = RTCConfiguration(iceServers=ice_servers) if ice_servers else RTCConfiguration()
        self._pc = RTCPeerConnection(configuration=config)
        self._audio_source = WebRTCAudioSource()
        self._generator = None

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

    async def close(self):
        """Tear down the peer connection."""
        self.stop_audio()
        await self._pc.close()
        log.info("Session closed")
