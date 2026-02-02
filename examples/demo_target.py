"""
DEMO TARGET: A sample Python file to visualize.

This demonstrates various code structures that will be
rendered as different parts of the organism.
"""

from dataclasses import dataclass
from typing import Optional, List
import json


# =============================================================================
# CLASSES (Organs)
# =============================================================================

@dataclass
class User:
    """A user in the system."""
    id: int
    name: str
    email: str
    active: bool = True


class UserRepository:
    """Repository for managing users."""

    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self._cache: dict[int, User] = {}

    def get(self, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        if user_id in self._cache:
            return self._cache[user_id]
        return self._load_from_disk(user_id)

    def save(self, user: User) -> None:
        """Save a user."""
        self._cache[user.id] = user
        self._persist_to_disk(user)

    def _load_from_disk(self, user_id: int) -> Optional[User]:
        """Load user from disk storage."""
        try:
            with open(f"{self.storage_path}/{user_id}.json") as f:
                data = json.load(f)
                return User(**data)
        except FileNotFoundError:
            return None

    def _persist_to_disk(self, user: User) -> None:
        """Persist user to disk storage."""
        with open(f"{self.storage_path}/{user.id}.json", "w") as f:
            json.dump({
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "active": user.active,
            }, f)


class UserService:
    """Service layer for user operations."""

    def __init__(self, repository: UserRepository):
        self.repository = repository

    def create_user(self, name: str, email: str) -> User:
        """Create a new user."""
        user_id = self._generate_id()
        user = User(id=user_id, name=name, email=email)
        self.repository.save(user)
        return user

    def get_user(self, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        return self.repository.get(user_id)

    def deactivate_user(self, user_id: int) -> bool:
        """Deactivate a user."""
        user = self.repository.get(user_id)
        if user:
            user.active = False
            self.repository.save(user)
            return True
        return False

    def _generate_id(self) -> int:
        """Generate a unique user ID."""
        import time
        return int(time.time() * 1000)


# =============================================================================
# FUNCTIONS (Tissues)
# =============================================================================

def validate_email(email: str) -> bool:
    """Validate an email address."""
    return "@" in email and "." in email.split("@")[1]


def format_user_display(user: User) -> str:
    """Format a user for display."""
    status = "active" if user.active else "inactive"
    return f"{user.name} <{user.email}> ({status})"


def batch_create_users(service: UserService, user_data: List[dict]) -> List[User]:
    """Create multiple users at once."""
    users = []
    for data in user_data:
        if validate_email(data["email"]):
            user = service.create_user(data["name"], data["email"])
            users.append(user)
    return users


# =============================================================================
# DEAD CODE (will be marked as necrotic)
# =============================================================================

def unused_function():
    """This function is never called - dead code."""
    print("I'm never used!")


class UnusedClass:
    """This class is never instantiated - dead code."""

    def unused_method(self):
        pass


# =============================================================================
# COMPLEX FUNCTION (will show as stressed/inflamed)
# =============================================================================

def complex_processor(data: dict, config: dict) -> dict:
    """A function with high cyclomatic complexity."""
    result = {}

    if data.get("type") == "A":
        if data.get("subtype") == "A1":
            if config.get("mode") == "fast":
                result["processed"] = True
                result["method"] = "fast_a1"
            elif config.get("mode") == "accurate":
                result["processed"] = True
                result["method"] = "accurate_a1"
            else:
                result["processed"] = False
                result["error"] = "unknown mode"
        elif data.get("subtype") == "A2":
            for item in data.get("items", []):
                if item.get("valid"):
                    result[item["id"]] = item["value"]
                else:
                    if config.get("strict"):
                        raise ValueError(f"Invalid item: {item}")
                    else:
                        result[item["id"]] = None
    elif data.get("type") == "B":
        if config.get("enabled"):
            result["type_b"] = True
            try:
                result["value"] = int(data["value"])
            except (ValueError, KeyError):
                result["value"] = 0
        else:
            result["skipped"] = True

    return result


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Main entry point."""
    repo = UserRepository("/tmp/users")
    service = UserService(repo)

    # Create a user
    user = service.create_user("Alice", "alice@example.com")
    print(format_user_display(user))

    # Get the user
    retrieved = service.get_user(user.id)
    if retrieved:
        print(f"Retrieved: {format_user_display(retrieved)}")


if __name__ == "__main__":
    main()
