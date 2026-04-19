#!/usr/bin/env python3
"""
Controlla la casella Gmail di Claudio e risponde automaticamente alle email non lette.
"""

import imaplib
import smtplib
import email
import email.utils
import re
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("email_responder")

GMAIL_USER = "djannons84@gmail.com"
GMAIL_APP_PASS = "bwzs yzbg oujy sung"

SYSTEM_PROMPT = """Sei Claudio, l'assistente personale AI di Marco.
Stai rispondendo a una email ricevuta sulla tua casella (djannons84@gmail.com).
Rispondi in modo cortese, conciso e naturale. 
Se la mail è in italiano rispondi in italiano, se è in inglese in inglese.
Firma sempre come "Claudio (AI assistant di Marco)".
Non inventare informazioni su Marco che non conosci.
Se ti fanno domande tecniche su come funzioni, puoi spiegare che sei un agente AI basato su Claude di Anthropic, che giri in Docker, e che Marco ti contatta via Telegram."""


def decode_str(s):
    if s is None:
        return ""
    parts = decode_header(s)
    result = ""
    for part, enc in parts:
        if isinstance(part, bytes):
            result += part.decode(enc or "utf-8", errors="replace")
        else:
            result += part
    return result


def get_text_body(msg):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                charset = part.get_content_charset() or "utf-8"
                body += part.get_payload(decode=True).decode(charset, errors="replace")
    else:
        charset = msg.get_content_charset() or "utf-8"
        body = msg.get_payload(decode=True).decode(charset, errors="replace")
    return body.strip()


def generate_reply(subject, sender_name, body):
    import subprocess, os
    prompt = f"""{SYSTEM_PROMPT}

Hai ricevuto questa email:

Da: {sender_name}
Oggetto: {subject}

Testo:
{body[:3000]}

Scrivi una risposta appropriata."""

    result = subprocess.run(
        ["claude", "-p", prompt, "--model", "claude-haiku-4-5"],
        capture_output=True, text=True, timeout=60,
        env={**os.environ}
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error: {result.stderr}")
    return result.stdout.strip()


def send_reply(to_addr, to_name, subject, body, message_id, references):
    msg = MIMEMultipart("alternative")
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    msg["Subject"] = reply_subject
    msg["From"] = f"Claudio <{GMAIL_USER}>"
    msg["To"] = f"{to_name} <{to_addr}>" if to_name else to_addr
    if message_id:
        msg["In-Reply-To"] = message_id
        msg["References"] = f"{references} {message_id}".strip() if references else message_id

    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASS)
        server.sendmail(GMAIL_USER, to_addr, msg.as_string())
    log.info(f"Risposta inviata a {to_addr} — Oggetto: {reply_subject}")


def check_and_reply():
    log.info("Controllo nuove email...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_USER, GMAIL_APP_PASS)
    mail.select("INBOX")

    _, data = mail.search(None, "UNSEEN")
    uids = data[0].split()
    log.info(f"Email non lette: {len(uids)}")

    for uid in uids:
        _, msg_data = mail.fetch(uid, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        from_raw = decode_str(msg.get("From", ""))
        subject = decode_str(msg.get("Subject", "(nessun oggetto)"))
        message_id = msg.get("Message-ID", "")
        references = msg.get("References", "")

        # Estrai nome e email mittente
        sender_name, sender_addr = email.utils.parseaddr(from_raw)

        # Non rispondere a mail inviate da noi stessi
        if sender_addr.lower() == GMAIL_USER.lower():
            mail.store(uid, "+FLAGS", "\\Seen")
            continue

        body = get_text_body(msg)
        log.info(f"Email da: {sender_addr} — Oggetto: {subject}")

        # Genera risposta
        reply = generate_reply(subject, sender_name or sender_addr, body)

        # Invia risposta
        send_reply(sender_addr, sender_name, subject, reply, message_id, references)

        # Marca come letta
        mail.store(uid, "+FLAGS", "\\Seen")

    mail.logout()
    log.info("Controllo completato.")


if __name__ == "__main__":
    check_and_reply()
