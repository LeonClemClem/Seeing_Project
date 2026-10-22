"""`seeing-create-user`: create an app account, or update an existing one with --update.

Sign-up only creates `user` accounts; use this to create the first administrator and the shared
CosmoDrôme team account. The password is never a command-line argument (process lists): it is
prompted (recommended), or read from $SEEING_USER_PASSWORD for non-interactive runs (an inline
`VAR=... command` still lands in shell history; prefer exporting it from a secret store).
Changing a password ends all the account's sessions.

    poetry run seeing-create-user --email admin@example.org --role admin
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import delete, select

from seeing_api.auth import MIN_PASSWORD_LENGTH, hash_password, normalize_email
from seeing_db import User, UserRole, UserSession, make_engine, make_session_factory

PASSWORD_ENV = "SEEING_USER_PASSWORD"  # noqa: S105 - the name of an environment variable, not a password


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create (or with --update, modify) an app account.")
    parser.add_argument("--email", required=True, help="login e-mail (stored lower-cased)")
    parser.add_argument(
        "--role", choices=[r.value for r in UserRole], help="account type (new accounts: user; --update: unchanged)"
    )
    parser.add_argument("--display-name", help="name shown in the app")
    parser.add_argument(
        "--update", action="store_true", help="the account exists: set its password, role and display name"
    )
    return parser.parse_args(argv)


def read_password() -> str:
    """Password from $SEEING_USER_PASSWORD, else prompted twice on the terminal."""
    password = os.environ.get(PASSWORD_ENV)
    if password is None:
        password = getpass.getpass("Password: ")
        if getpass.getpass("Repeat password: ") != password:
            sys.exit("Passwords do not match.")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Password too short: at least {MIN_PASSWORD_LENGTH} characters.")
    return password


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    email = normalize_email(args.email)
    engine = make_engine()
    try:
        with make_session_factory(engine)() as session:
            user = session.scalar(select(User).where(User.email == email))
            if user is not None and not args.update:
                sys.exit(f"An account already exists for {email} (use --update to change it).")
            if user is None and args.update:
                sys.exit(f"No account for {email}.")
            password_hash = hash_password(read_password())
            if user is None:
                user = User(email=email)
                session.add(user)
            else:
                # A new password ends every existing session (e.g. one opened by someone else).
                session.execute(delete(UserSession).where(UserSession.user_id == user.id))
            user.password_hash = password_hash
            if args.role is not None or user.role is None:
                user.role = UserRole(args.role or UserRole.user.value)
            if args.display_name is not None:
                user.display_name = args.display_name.strip() or None
            session.commit()
            print(f"{'Updated' if args.update else 'Created'} {user.role.value} account {email} (id {user.id}).")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
