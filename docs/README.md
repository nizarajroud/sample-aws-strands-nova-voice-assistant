# Documentation — Nova Voice Assistant

This folder contains all architecture and flow documentation for the project.

## Diagrams

| File | Format | Description |
|------|--------|-------------|
| `message-journey.d2` / `.svg` | D2 | **Start here.** Simple 10-step message journey: user voice → response voice |
| `nova-voice-full-architecture.d2` / `.svg` | D2 | Full architecture with AWS regions (us-east-1, ca-central-1) and local WSL |
| `nova-voice-process-flow.d2` / `.svg` | D2 | Detailed internal process flow (frontend/backend components) |
| `nova-voice-assistant-architecture.drawio` | draw.io | AWS service-icon architecture diagram |

## Message Journey (current `main` branch — Knowledge Base mode)

```
1.  User speaks into microphone (voice)
2.  Browser → Backend: audio PCM16 base64 over WebSocket
3.  Backend → Nova 2 Sonic: bidirectional stream (audioInput)
4.  Nova Sonic → Backend: toolUse event (needs data)
5.  Backend → Knowledge Base: retrieve_and_generate (the question)
6.  Knowledge Base → Backend: text answer (~3-4s)
7.  Backend → Nova Sonic: toolResult (answer text)
8.  Nova Sonic → Backend: audioOutput (generated speech)
9.  Backend → Browser: audio base64 over WebSocket
10. Browser → User: plays the response (speakers)
```

## Who talks to what

| Component | Location | Talks to | Protocol |
|-----------|----------|----------|----------|
| Browser (React) | Windows Chrome | Backend | WebSocket (ws://WSL-IP:8080) |
| Backend (Python) | WSL2 Ubuntu | Nova Sonic | Bedrock bidirectional stream (CRT) |
| Backend (Python) | WSL2 Ubuntu | Knowledge Base | boto3 retrieve_and_generate |
| Nova 2 Sonic | AWS us-east-1 | — | STT + LLM + TTS (single model) |
| Knowledge Base | AWS ca-central-1 | — | Vector search + Claude Haiku |

## Cross-cutting behaviors

- **Barge-in**: when the user speaks while Nova is talking, Nova sends an interruption signal (`contentEnd` with `stopReason=INTERRUPTED`), and the frontend clears its audio buffer immediately.
- **Session refresh**: every 4.5 minutes the backend transparently closes and reopens the Nova Sonic stream (which has an 8-min hard timeout), re-injecting conversation history so context is preserved.

## Two operating modes (branches)

| Branch | Backend behavior |
|--------|------------------|
| `main` | Routes all questions to the Bedrock **Knowledge Base** |
| `feature/mcp-bridge` | Routes to a **Strands agent** with kiro-cli MCP servers (Notion, GitHub, memory, etc.) |
