from abc import ABC, abstractmethod


class PaymentProvider(ABC):
    """Future CryptoBot / fiat adapters implement this. Stars are native invoices."""

    name: str

    @abstractmethod
    async def create_invoice(self, *, user_id: int, kopecks: int) -> str:
        raise NotImplementedError
