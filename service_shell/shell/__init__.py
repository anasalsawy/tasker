"""Hands Always-On Shell - resident tray presence for the Hands persona.

Package layout:
    shell.config      - config.toml loading + env overrides
    shell.context     - ambient awareness sampler (foreground window via ctypes)
    shell.audio       - mic capture, VAD gate, rolling buffer (never persists raw audio)
    shell.wake        - wake engine ladder + wake->ack state machine
    shell.persona     - Tasker-backend / DL-Companion SSE client (mirrors
                        backend/persona_client.py event contract exactly)
    shell.chain       - intent -> persona -> last_response pipeline (fire-and-forget)
    shell.httpd       - localhost API for the UI + voice lanes
    shell.tray        - pystray presence with icon state machine
    shell.notify      - ack: sound + topmost toast, all stdlib/ctypes

Privacy invariants (hard rules):
    * raw microphone audio NEVER touches disk or network - only feature/classifier
      scores leave the audio thread, and even those stay in-process.
    * No keylogging, ever - not implemented anywhere in this package.
    * Screenshots and activity persistence are opt-in flags, both default false.
"""
__version__ = "0.9.0"
