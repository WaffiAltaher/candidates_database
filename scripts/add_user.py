#!/usr/bin/env python3
"""Generate an AUTH_USERS JSON entry for a new user.

Usage:
    poetry run python add_user.py
    poetry run python add_user.py alice
"""

import getpass
import hashlib
import json
import sys


def main():
    username = sys.argv[1] if len(sys.argv) > 1 else input("Username: ")
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        print("Passwords do not match.")
        sys.exit(1)

    hashed = hashlib.sha256(password.encode()).hexdigest()
    print(f"\nAdd this to your AUTH_USERS env var:\n")
    print(f'  "{username}": "{hashed}"')
    print(f"\nFull single-user example:")
    print(f'  AUTH_USERS=\'{json.dumps({username: hashed})}\'')


if __name__ == "__main__":
    main()
