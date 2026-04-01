"""
Application Interfaces (Ports)

Abstract interfaces that define contracts between the application
layer and infrastructure adapters. These are the "ports" in
hexagonal architecture.
"""

from .ai_client import AIClient
from .audio_resolver import AudioResolver
from .voice_adapter import VoiceAdapter

__all__ = [
    "AudioResolver",
    "VoiceAdapter",
    "AIClient",
]
