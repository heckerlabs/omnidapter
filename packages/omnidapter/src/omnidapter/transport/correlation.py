from uuid import uuid4


def new_correlation_id() -> str:
    return uuid4().hex
