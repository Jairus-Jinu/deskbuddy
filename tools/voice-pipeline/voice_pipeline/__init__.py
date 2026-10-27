"""DeskBuddy voice pipeline — laptop-hosted STT -> LLM -> TTS prototype."""

from .audio import AudioError, is_silent, play_wav, record_wav, temp_wav, wav_duration
from .audio_io import AudioDeviceError, Microphone, Speaker
from .brain import Brain, BrainConfig, BrainError
from .conversation import (
    ConversationSettings,
    ConversationSession,
    converse,
    pcm_to_wav,
    split_sentences,
)
from .factory import build_brain, selected_provider
from .groq_brain import GroqBrain, GroqConfig, GroqError
from .kokoro_tts import KokoroError, KokoroTTS
from .piper_tts import PiperError, PiperTTS
from .pipeline import Conversation, voice_loop
from .providers import (
    LanguageModel,
    SpeechToText,
    StreamingLanguageModel,
    TextToSpeech,
    Turn,
)
from .vad import SileroVad, TurnDetector, VadError, ensure_model
from .wake_word import WakeWord, WakeWordError

__all__ = [
    "AudioDeviceError",
    "AudioError",
    "Brain",
    "BrainConfig",
    "BrainError",
    "Conversation",
    "ConversationSession",
    "ConversationSettings",
    "GroqBrain",
    "GroqConfig",
    "GroqError",
    "KokoroError",
    "KokoroTTS",
    "LanguageModel",
    "Microphone",
    "PiperError",
    "PiperTTS",
    "SileroVad",
    "Speaker",
    "SpeechToText",
    "StreamingLanguageModel",
    "TextToSpeech",
    "Turn",
    "TurnDetector",
    "VadError",
    "WakeWord",
    "WakeWordError",
    "build_brain",
    "converse",
    "ensure_model",
    "is_silent",
    "pcm_to_wav",
    "play_wav",
    "record_wav",
    "selected_provider",
    "split_sentences",
    "temp_wav",
    "voice_loop",
    "wav_duration",
]
