from getpass import getpass
import re

import keyring


def main() -> int:
    try:
        password = "".join(getpass("Enter a newly created Google app password (input hidden): ").split())
        if not password:
            print("No password entered; nothing was saved.")
            return 1
        if not re.fullmatch(r"[A-Za-z0-9]{16}", password):
            print("Invalid format. Enter the 16-character Google app password; spaces are optional.")
            return 1
        keyring.set_password("Gas Guardian", "smtp-password", password)
    except Exception as exc:
        print(f"Could not save the app password in Windows Credential Manager: {exc}")
        return 1
    print("Google app password saved securely in Windows Credential Manager.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())