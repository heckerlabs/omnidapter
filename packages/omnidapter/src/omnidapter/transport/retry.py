from pydantic import BaseModel


class RetryPolicy(BaseModel):
    max_attempts: int = 3
    base_delay_seconds: float = 0.1

    @classmethod
    def default(cls) -> "RetryPolicy":
        return cls()

    @classmethod
    def disabled(cls) -> "RetryPolicy":
        return cls(max_attempts=1)
