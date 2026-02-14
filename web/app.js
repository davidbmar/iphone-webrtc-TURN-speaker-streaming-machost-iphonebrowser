"use strict";

// --- DOM refs ---
const wsDot = document.getElementById("ws-dot");
const wsStatus = document.getElementById("ws-status");
const rtcDot = document.getElementById("rtc-dot");
const rtcStatus = document.getElementById("rtc-status");
const tokenInput = document.getElementById("token-input");
const connectBtn = document.getElementById("connect-btn");
const controlsSection = document.getElementById("controls-section");
const voiceSelect = document.getElementById("voice-select");
const startBtn = document.getElementById("start-btn");
const stopBtn = document.getElementById("stop-btn");
const ttsSection = document.getElementById("tts-section");
const ttsInput = document.getElementById("tts-input");
const speakBtn = document.getElementById("speak-btn");
const debugLog = document.getElementById("debug-log");

// --- State ---
let iceServers = window.__CONFIG__ || [];
let ws = null;
let pc = null;
let audioEl = null;

// --- Debug logging ---
function log(msg, cls = "info") {
    const line = document.createElement("div");
    line.className = cls;
    const ts = new Date().toLocaleTimeString("en-US", { hour12: false });
    line.textContent = `[${ts}] ${msg}`;
    debugLog.appendChild(line);
    debugLog.scrollTop = debugLog.scrollHeight;
    console.log(`[${cls}] ${msg}`);
}

// --- WebSocket ---
function sendMsg(type, payload = {}) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type, ...payload }));
}

function setWsState(state) {
    wsDot.className = "status-dot " + state;
    const labels = { connected: "Connected", error: "Disconnected", connecting: "Connecting..." };
    wsStatus.textContent = labels[state] || state;
}

function connect() {
    const token = tokenInput.value.trim();
    if (!token) { log("Enter a token first", "error"); return; }

    connectBtn.disabled = true;
    setWsState("connecting");

    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws`);

    ws.onopen = () => {
        log("WebSocket opened, sending hello...");
        sendMsg("hello", { token });
    };

    ws.onmessage = (ev) => {
        let msg;
        try { msg = JSON.parse(ev.data); } catch { log("Bad JSON from server", "error"); return; }
        handleMessage(msg);
    };

    ws.onerror = () => {
        log("WebSocket error", "error");
        setWsState("error");
        connectBtn.disabled = false;
    };

    ws.onclose = () => {
        log("WebSocket closed");
        setWsState("error");
        connectBtn.disabled = false;
        controlsSection.classList.add("hidden");
        ttsSection.classList.add("hidden");
        cleanupWebRTC();
    };
}

function handleMessage(msg) {
    switch (msg.type) {
        case "hello_ack":
            log("Authenticated! Received " + msg.voices.length + " voices", "success");
            // Use TURN credentials from server (Twilio) if provided
            if (msg.ice_servers && msg.ice_servers.length > 0) {
                iceServers = msg.ice_servers;
                log("Got " + iceServers.length + " ICE servers from server", "success");
            }
            setWsState("connected");
            populateVoices(msg.voices);
            controlsSection.classList.remove("hidden");
            ttsSection.classList.remove("hidden");
            startWebRTC();
            break;

        case "webrtc_answer":
            log("Received WebRTC answer");
            handleWebRTCAnswer(msg.sdp);
            break;

        case "pong":
            break;

        case "error":
            log("Server error: " + msg.message, "error");
            break;

        default:
            log("Unknown message type: " + msg.type);
    }
}

// --- Voice dropdown ---
function populateVoices(voices) {
    // Clear existing options using safe DOM methods
    while (voiceSelect.firstChild) {
        voiceSelect.removeChild(voiceSelect.firstChild);
    }
    voices.forEach((v) => {
        const opt = document.createElement("option");
        opt.value = v.id;
        opt.textContent = `${v.name} — ${v.description}`;
        voiceSelect.appendChild(opt);
    });
    voiceSelect.disabled = false;
}

// --- WebRTC ---
async function startWebRTC() {
    log("Starting WebRTC negotiation...");
    setRtcState("connecting");

    const config = { iceServers: iceServers.length > 0 ? iceServers : undefined };
    pc = new RTCPeerConnection(config);

    // Receive-only audio
    pc.addTransceiver("audio", { direction: "recvonly" });

    pc.onicecandidate = (ev) => {
        if (ev.candidate) {
            const typ = ev.candidate.candidate.match(/typ (\w+)/);
            log("ICE candidate: " + (typ ? typ[1] : "unknown"));
        }
    };

    pc.oniceconnectionstatechange = () => {
        log("ICE state: " + pc.iceConnectionState);
        if (pc.iceConnectionState === "connected" || pc.iceConnectionState === "completed") {
            setRtcState("connected");
            startBtn.disabled = false;
        } else if (pc.iceConnectionState === "failed" || pc.iceConnectionState === "disconnected") {
            setRtcState("error");
        }
    };

    pc.ontrack = (ev) => {
        log("Received remote audio track", "success");
        if (audioEl) { audioEl.srcObject = null; audioEl.remove(); }
        audioEl = document.createElement("audio");
        audioEl.autoplay = true;
        audioEl.playsInline = true;
        audioEl.srcObject = ev.streams[0] || new MediaStream([ev.track]);
        document.body.appendChild(audioEl);
    };

    // Create offer and wait for ICE gathering to complete
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    // Wait for ICE gathering to finish (aiortc needs all candidates bundled)
    await waitForIceGathering(pc);

    log("ICE gathering complete, sending offer");
    sendMsg("webrtc_offer", { sdp: pc.localDescription.sdp });
}

function waitForIceGathering(pc) {
    return new Promise((resolve) => {
        if (pc.iceGatheringState === "complete") { resolve(); return; }
        pc.onicegatheringstatechange = () => {
            if (pc.iceGatheringState === "complete") resolve();
        };
    });
}

async function handleWebRTCAnswer(sdp) {
    if (!pc) { log("No PeerConnection for answer", "error"); return; }
    try {
        await pc.setRemoteDescription({ type: "answer", sdp });
        log("Remote description set", "success");
    } catch (e) {
        log("Failed to set answer: " + e.message, "error");
    }
}

function setRtcState(state) {
    rtcDot.className = "status-dot " + state;
    const labels = {
        connected: "WebRTC connected",
        error: "WebRTC failed",
        connecting: "Negotiating..."
    };
    rtcStatus.textContent = labels[state] || state;
}

function cleanupWebRTC() {
    if (pc) { pc.close(); pc = null; }
    if (audioEl) { audioEl.srcObject = null; audioEl.remove(); audioEl = null; }
    setRtcState("");
    startBtn.disabled = true;
    stopBtn.disabled = true;
}

// --- Start / Stop audio ---
function startAudio() {
    const voiceId = voiceSelect.value;
    if (!voiceId) { log("Select a voice first", "error"); return; }
    log("Starting audio: " + voiceId);
    sendMsg("start", { voice_id: voiceId });
    startBtn.disabled = true;
    stopBtn.disabled = false;

    // iOS Safari: ensure audio element plays (needs gesture)
    if (audioEl) {
        audioEl.play().catch(() => log("Audio play blocked by browser", "error"));
    }
}

function stopAudio() {
    log("Stopping audio");
    sendMsg("stop");
    startBtn.disabled = false;
    stopBtn.disabled = true;
}

// --- TTS ---
function speakText() {
    const text = ttsInput.value.trim();
    if (!text) { log("Enter text to speak", "error"); return; }
    log("Speaking: " + text);
    sendMsg("speak", { text });

    // iOS Safari: ensure audio element plays (needs gesture)
    if (audioEl) {
        audioEl.play().catch(() => log("Audio play blocked by browser", "error"));
    }
}

// --- Keepalive ---
setInterval(() => { sendMsg("ping"); }, 25000);

// --- Event listeners ---
connectBtn.addEventListener("click", connect);
startBtn.addEventListener("click", startAudio);
stopBtn.addEventListener("click", stopAudio);
speakBtn.addEventListener("click", speakText);

// Allow Enter key to connect
tokenInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") connect();
});

// Allow Enter key to speak
ttsInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") speakText();
});

log("Client ready. Enter token and connect.");
