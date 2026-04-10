"""
Main message handler: text, voice, photos, documents.
"""

import logging
from pathlib import Path

from aiogram import Router
from aiogram.types import Message, FSInputFile, InputFile

from bot.auth import is_allowed_user
from bot.config import UPLOADS_DIR, VOICE_RESPONSE_MAX_LENGTH, SEND_VOICE_DIR, SEND_FILE_DIR
from bot.text_cleaner import clean_for_tts, split_message
from bot.voice import transcribe, synthesize
from bot.monitor import emit
from bot.prompts import PLANNING_PREFIX
from bot.handlers._state import (
    bridge, topic_map, get_thread_id, get_project_for_message,
    plan_mode, voice_requested, last_response,
)

log = logging.getLogger("claudio.messages")

router = Router()


async def _download_file(message: Message, prefix: str, suffix: str) -> Path | None:
    """Generic file download from Telegram."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    if prefix == "voice" and message.voice:
        file = await message.bot.get_file(message.voice.file_id)
        local_path = UPLOADS_DIR / f"voice_{message.voice.file_unique_id}.ogg"
    elif prefix == "photo" and message.photo:
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        ext = Path(file.file_path).suffix or suffix
        local_path = UPLOADS_DIR / f"{photo.file_unique_id}{ext}"
    elif prefix == "doc" and message.document:
        doc = message.document
        file = await message.bot.get_file(doc.file_id)
        local_path = UPLOADS_DIR / (doc.file_name or f"{doc.file_unique_id}{suffix}")
    else:
        return None

    await message.bot.download_file(file.file_path, local_path)
    return local_path


@router.message()
async def handle_message(message: Message) -> None:
    if not message.from_user:
        return

    if not is_allowed_user(message.from_user.id):
        return

    if message.text and message.text.startswith("/"):
        return

    # Build prompt from text + attachments
    parts: list[str] = []

    # Voice messages — transcribe and keep file
    if message.voice:
        voice_path = await _download_file(message, "voice", ".ogg")
        if voice_path:
            await message.bot.send_chat_action(message.chat.id, "typing")
            transcription = await transcribe(voice_path)
            if transcription:
                parts.append(
                    f"L'utente ha inviato un messaggio vocale.\n"
                    f"File audio salvato in: {voice_path}\n"
                    f"Trascrizione: {transcription}"
                )
                log.info(f"Voice transcribed: {transcription[:80]}...")

    # Photos
    if message.photo:
        photo_path = await _download_file(message, "photo", ".jpg")
        if photo_path:
            parts.append(f"L'utente ha inviato un'immagine. Leggila con il tool Read da: {photo_path}")

    # Documents
    if message.document:
        doc_path = await _download_file(message, "doc", "")
        if doc_path:
            parts.append(f"L'utente ha inviato un file: {doc_path}")

    # Text or caption
    text = message.text or message.caption
    if text:
        parts.append(text)

    if not parts:
        return

    prompt = "\n\n".join(parts)

    project_name_for_emit, _ = get_project_for_message(message)
    await emit("message_received", {
        "project": project_name_for_emit or "general",
        "is_voice": bool(message.voice),
        "text_preview": prompt[:100],
    })

    # Planning mode
    chat_key = (message.chat.id, get_thread_id(message))
    if chat_key in plan_mode:
        plan_mode.discard(chat_key)
        prompt = PLANNING_PREFIX + prompt

    project_name, project_path = get_project_for_message(message)

    await message.bot.send_chat_action(message.chat.id, "typing")
    thinking_msg = await message.reply("Sto pensando...")

    try:
        response = await bridge.query(
            chat_id=message.chat.id,
            prompt=prompt,
            project_name=project_name,
            project_path=project_path,
        )

        await thinking_msg.delete()

        # Determine response mode
        # Claude can suppress voice by including [NO_VOICE] in the response
        suppress_voice = "[NO_VOICE]" in response
        if suppress_voice:
            response = response.replace("[NO_VOICE]", "").strip()

        is_voice_input = bool(message.voice)
        force_voice = chat_key in voice_requested
        if force_voice:
            voice_requested.discard(chat_key)

        # Save for /text command
        last_response[chat_key] = response

        should_voice = (is_voice_input or force_voice) and not suppress_voice and len(response) < VOICE_RESPONSE_MAX_LENGTH

        if should_voice:
            clean_text = clean_for_tts(response)
            ogg_path = await synthesize(clean_text) if clean_text else None
            if ogg_path and ogg_path.exists():
                await message.answer_voice(FSInputFile(ogg_path))
                ogg_path.unlink(missing_ok=True)
            else:
                for chunk in split_message(response):
                    await message.reply(chunk)
        else:
            for chunk in split_message(response):
                await message.reply(chunk)

        # Check if Claude dropped files in the send queues
        await _flush_send_queues(message)

    except Exception as e:
        log.error(f"Claude error: {e}", exc_info=True)
        error_str = str(e).lower()
        if "rate_limit" in error_str or "429" in error_str:
            user_msg = "Troppo traffico. Riprova tra qualche secondo."
        elif "timeout" in error_str:
            user_msg = "La richiesta ha impiegato troppo tempo. Riprova."
        elif "overloaded" in error_str:
            user_msg = "Il server Claude è sovraccarico. Riprova tra qualche minuto."
        else:
            user_msg = f"Errore: {e}"
        await thinking_msg.edit_text(user_msg)


async def _flush_send_queues(message: Message) -> None:
    """Send any files that Claude Code dropped in the send queues."""
    # Voice files
    if SEND_VOICE_DIR.exists():
        for f in sorted(SEND_VOICE_DIR.iterdir()):
            if f.is_file() and f.suffix in (".ogg", ".wav", ".mp3"):
                try:
                    await message.answer_voice(FSInputFile(f))
                    log.info(f"Sent queued voice: {f.name}")
                except Exception as e:
                    log.error(f"Failed to send voice {f.name}: {e}")
                finally:
                    f.unlink(missing_ok=True)

    # Generic files
    if SEND_FILE_DIR.exists():
        for f in sorted(SEND_FILE_DIR.iterdir()):
            if f.is_file():
                try:
                    await message.answer_document(FSInputFile(f))
                    log.info(f"Sent queued file: {f.name}")
                except Exception as e:
                    log.error(f"Failed to send file {f.name}: {e}")
                finally:
                    f.unlink(missing_ok=True)
