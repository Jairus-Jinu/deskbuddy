"""DeskBuddy voice pipeline — laptop-hosted STT -> LLM -> TTS prototype."""

from .audio import AudioError, is_silent, play_wav, record_wav, temp_wav, wav_duration
from .brain import Brain, BrainConfig, BrainError
from .pipeline import Conversation, Turn, voice_loop

__all__ = [
    "AudioError",
    "Brain",
    "BrainConfig",
    "BrainError",
    "Conversation",
    "Turn",
    "is_silent",
    "play_wav",
    "record_wav",
    "temp_wav",
    "voice_loop",
    "wav_duration",
]
