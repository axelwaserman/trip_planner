"""Auth domain exceptions."""


class UserNotFoundError(Exception):
    """Raised by UserRepository.get_user when the username does not exist."""

    def __init__(self, username: str) -> None:
        super().__init__(f"User not found: {username!r}")
        self.username = username
