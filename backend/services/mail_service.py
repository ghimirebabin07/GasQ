import logging
import smtplib
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import get_settings

logger = logging.getLogger("gasq.mail")


class MailProvider(ABC):
    @abstractmethod
    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        pass


class ConsoleMailProvider(MailProvider):
    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        logger.info(
            "\n========================================\n"
            "[ConsoleMailProvider] To: %s\n"
            "Subject: %s\n"
            "Body: %s\n"
            "========================================",
            to_email,
            subject,
            body,
        )
        return True


class SmtpMailProvider(MailProvider):
    def __init__(self):
        self.settings = get_settings()

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        if not self.settings.smtp_host:
            logger.warning("SMTP host is not configured; falling back to logging")
            return ConsoleMailProvider().send_email(to_email, subject, body)

        try:
            msg = MIMEMultipart()
            msg["From"] = self.settings.smtp_username or "no-reply@gasq.local"
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                if self.settings.smtp_username and self.settings.smtp_password:
                    server.login(self.settings.smtp_username, self.settings.smtp_password)
                server.send_message(msg)
            return True
        except Exception as exc:
            logger.error("Failed to send email via SMTP to %s: %s", to_email, exc)
            return False


def get_mail_provider() -> MailProvider:
    settings = get_settings()
    if settings.mail_provider.strip().lower() == "smtp":
        return SmtpMailProvider()
    return ConsoleMailProvider()
