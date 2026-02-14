"""
Authentication service for Plex OAuth.

Extracted from ui/login_frame.py. No UI dependencies.
"""

import logging
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
from utils.constants import OAUTH_LOGIN_TIMEOUT


def start_oauth():
    """
    Create a MyPlexPinLogin and return the OAuth URL.

    Returns:
        tuple: (pin_login, oauth_url)
    """
    logging.info("Starting OAuth login process...")
    pin_login = MyPlexPinLogin(oauth=True)
    logging.info("PIN login created successfully")

    oauth_url = pin_login.oauthUrl()
    logging.info(f"OAuth URL generated: {oauth_url}")

    return pin_login, oauth_url


def poll_oauth(pin_login):
    """
    Non-blocking check if OAuth login has completed.

    Args:
        pin_login: MyPlexPinLogin instance from start_oauth()

    Returns:
        MyPlexAccount if authenticated, None if still pending
    """
    # checkLogin() returns True if the user has authenticated
    if pin_login.checkLogin():
        token = pin_login.token
        if token:
            logging.info("OAuth token received successfully")
            account = MyPlexAccount(token=token)
            logging.info(f"Successfully authenticated as: {account.username}")
            return account
    return None


def wait_for_oauth(pin_login, timeout=OAUTH_LOGIN_TIMEOUT):
    """
    Blocking wait for OAuth completion (used for background thread approach).

    Args:
        pin_login: MyPlexPinLogin instance
        timeout: Max seconds to wait

    Returns:
        MyPlexAccount if authenticated, None if timed out
    """
    token = None

    def on_login(t):
        nonlocal token
        token = t

    pin_login.run(callback=on_login, timeout=timeout)

    if token:
        logging.info("OAuth token received successfully")
        account = MyPlexAccount(token=token)
        logging.info(f"Successfully authenticated as: {account.username}")
        return account

    logging.warning("OAuth login failed or timed out")
    return None
