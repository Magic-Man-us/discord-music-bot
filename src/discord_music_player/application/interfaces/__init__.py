"""
Application Interfaces (Ports)

Abstract interfaces that define contracts between the application
layer and infrastructure adapters. These are the "ports" in
hexagonal architecture.
"""

from discord_music_player.application.interfaces.ai_client import AIClient
from discord_music_player.application.interfaces.audio_resolver import AudioResolver
from discord_music_player.application.interfaces.voice_adapter import VoiceAdapter

__all__ = [
    "AudioResolver",
    "VoiceAdapter",
    "AIClient",
]
