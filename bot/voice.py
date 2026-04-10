"""
Voice processing: STT (faster-whisper) + TTS (Qwen3-TTS via mlx-tts-api / Edge TTS fallback).
"""

import asyncio
import logging
import subprocess
import uuid
from pathlib import Path

import aiohttp
import edge_tts

from bot.config import (
    UPLOADS_DIR, TTS_HOST, TTS_LANGUAGE, TTS_MODEL_NAME,
    TTS_TIMEOUT_SECONDS, TTS_SAMPLE_RATE, OGG_BITRATE, EDGE_TTS_VOICE,
    WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
    WHISPER_LANGUAGE, WHISPER_BEAM_SIZE, STT_SAMPLE_RATE,
    get_runtime,
)

log = logging.getLogger("claudio.voice")

_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        log.info("Importing faster-whisper...")
        from faster_whisper import WhisperModel
        log.info(f"Loading WhisperModel ({WHISPER_MODEL}, {WHISPER_COMPUTE_TYPE})...")
        try:
            _whisper_model = WhisperModel(
                WHISPER_MODEL,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
            )
            log.info("Whisper model loaded successfully.")
        except Exception as e:
            log.error(f"Whisper model failed to load: {e}", exc_info=True)
            raise
    return _whisper_model


def _ffmpeg(args: list[str]) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y"] + args,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[:300]}")


def _ogg_to_wav(ogg_path: Path) -> Path:
    wav_path = ogg_path.with_suffix(".wav")
    _ffmpeg(["-i", str(ogg_path), "-ar", str(STT_SAMPLE_RATE), "-ac", "1", str(wav_path)])
    return wav_path


def _to_ogg(input_path: Path) -> Path:
    ogg_path = input_path.with_suffix(".ogg")
    _ffmpeg(["-i", str(input_path), "-c:a", "libopus", "-b:a", OGG_BITRATE, str(ogg_path)])
    return ogg_path


def _unique_path(prefix: str, suffix: str) -> Path:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOADS_DIR / f"{prefix}_{uuid.uuid4().hex[:12]}{suffix}"


async def transcribe(ogg_path: Path) -> str:
    """Transcribe a voice message (OGG) to text using faster-whisper."""
    from bot.monitor import emit
    await emit("stt_start")

    loop = asyncio.get_event_loop()
    start = asyncio.get_event_loop().time()

    def _do_transcribe():
        wav_path = _ogg_to_wav(ogg_path)
        try:
            model = _get_whisper_model()
            segments, info = model.transcribe(
                str(wav_path),
                language=WHISPER_LANGUAGE,
                beam_size=WHISPER_BEAM_SIZE,
            )
            text = " ".join(seg.text.strip() for seg in segments)
            log.info(f"Transcribed ({info.language}, {info.duration:.1f}s): {text[:100]}...")
            return text, info.duration
        finally:
            wav_path.unlink(missing_ok=True)

    text, audio_duration = await loop.run_in_executor(None, _do_transcribe)
    duration = asyncio.get_event_loop().time() - start

    await emit("stt_end", {
        "duration_s": round(duration, 1),
        "audio_duration_s": round(audio_duration, 1),
        "text_preview": text[:100] if text else "",
        "language": WHISPER_LANGUAGE,
    })

    return text


async def synthesize(text: str) -> Path | None:
    """Generate speech. Tries Qwen3-TTS first, falls back to Edge TTS."""
    from bot.monitor import emit

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    start = asyncio.get_event_loop().time()

    result = await _synthesize_qwen(text)
    engine = "qwen3-tts"
    if not result:
        log.info("Qwen3-TTS unavailable, falling back to Edge TTS")
        result = await _synthesize_edge(text)
        engine = "edge-tts"

    duration = asyncio.get_event_loop().time() - start
    if result:
        await emit("tts_end", {"engine": engine, "duration_s": round(duration, 1), "chars": len(text)})

    return result


async def _synthesize_qwen(text: str) -> Path | None:
    """Call Qwen3-TTS via mlx-tts-api on the host Mac."""
    wav_path = _unique_path("tts_qwen", ".wav")
    try:
        payload = {
            "model": TTS_MODEL_NAME,
            "input": text,
            "voice": get_runtime("TTS_VOICE", "ryan"),
            "language": TTS_LANGUAGE,
        }

        timeout = aiohttp.ClientTimeout(total=TTS_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{TTS_HOST}/v1/audio/speech", json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.warning(f"Qwen3-TTS returned {resp.status}: {body[:200]}")
                    return None

                wav_data = await resp.read()
                if not wav_data:
                    log.warning("Qwen3-TTS returned empty audio")
                    return None

                wav_path.write_bytes(wav_data)
                ogg_path = _to_ogg(wav_path)
                log.info(f"Qwen3-TTS synthesis complete ({len(text)} chars)")
                return ogg_path

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning(f"Qwen3-TTS connection failed: {e}")
        return None
    except RuntimeError as e:
        log.error(f"ffmpeg conversion failed: {e}")
        return None
    finally:
        wav_path.unlink(missing_ok=True)


async def _synthesize_edge(text: str) -> Path | None:
    """Fallback: Edge TTS (free Microsoft Neural voices)."""
    mp3_path = _unique_path("tts_edge", ".mp3")
    try:
        communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE)
        await communicate.save(str(mp3_path))

        ogg_path = _to_ogg(mp3_path)
        log.info("Edge TTS synthesis complete (fallback)")
        return ogg_path

    except Exception as e:
        log.error(f"Edge TTS failed: {e}", exc_info=True)
        return None
    finally:
        mp3_path.unlink(missing_ok=True)
