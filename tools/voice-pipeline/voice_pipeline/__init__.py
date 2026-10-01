"""DeskBuddy voice pipeline — laptop-hosted STT -> LLM -> TTS prototype."""

from .audio import AudioError, is_silent, play_wav, record_wav, temp_wav, wav_duration
from .brain import Brain, BrainConfig, BrainError
from .factory import build_brain, selected_provider
from .groq_brain import GroqBrain, GroqConfig, GroqError
from .piper_tts import PiperError, PiperTTS
from .pipeline import Conversation, voice_loop
from .providers import LanguageModel, SpeechToText, TextToSpeech, Turn

__all__ = [
    "AudioError",
    "Brain",
    "BrainConfig",
    "BrainError",
    "Conversation",
    "GroqBrain",
    "GroqConfig",
    "GroqError",
    "LanguageModel",
    "PiperError",
    "PiperTTS",
    "SpeechToText",
    "TextToSpeech",
    "Turn",
    "build_brain",
    "is_silent",
    "play_wav",
    "record_wav",
    "selected_provider",
    "temp_wav",
    "voice_loop",
    "wav_duration",
]
