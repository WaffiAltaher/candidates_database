#!/usr/bin/env python3
"""Generate an AUTH_USERS JSON entry for a new user.

Usage:
    poetry run python scripts/add_user.py [username]
"""

import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from candidates.passwords import hash_password  # noqa: E402


def main():
    username = sys.argv[1] if len(sys.argv) > 1 else input("Username: ")
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        print("Passwords do not match.")
        sys.exit(1)

    hashed = hash_password(password)
    print(f"\nAdd this to your AUTH_USERS env var:\n")
    print(f'  "{username}": "{hashed}"')
    print(f"\nFull single-user example:")
    print(f'  AUTH_USERS=\'{json.dumps({username: hashed})}\'')


if __name__ == "__main__":
    main()
