import smtplib

from email.message import EmailMessage

from app.config.settings import Settings


class EmailService:
    def __init__(self):
        self.config: Settings = Settings()

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.config.SMTP_SENDER
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(self.config.SMTP_HOST, self.config.SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(self.config.SMTP_USERNAME, self.config.SMTP_PASSWORD)
            smtp.send_message(message)
