import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("gasq.sms")


class SmsProvider(ABC):
    @abstractmethod
    def send_sms(self, phone: str, message: str) -> bool:
        pass


class ConsoleSmsProvider(SmsProvider):
    def send_sms(self, phone: str, message: str) -> bool:
        logger.info(
            "\n========================================\n"
            "[ConsoleSmsProvider] To: %s\n"
            "Message: %s\n"
            "========================================",
            phone,
            message,
        )
        return True


def get_sms_provider() -> SmsProvider:
    # Future paid providers (Twilio, Sparrow SMS, etc.) can be plugged here
    return ConsoleSmsProvider()
