"""
Authentication service for Plex OAuth.

Extracted from ui/login_frame.py. No UI dependencies.
"""

import logging
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin


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


