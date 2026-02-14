#!/usr/bin/env python3
"""
Comprehensive Error Handling Framework for PlexSubSetter
Provides custom exceptions, retry logic, error messages, and crash reporting.
"""

import logging
import traceback
import time
import functools
import os
from datetime import datetime
from typing import Callable, Optional, Any, Dict
from pathlib import Path


# ==================== CUSTOM EXCEPTIONS ====================

class PlexSubSetterError(Exception):
    """Base exception for all PlexSubSetter errors."""

    def __init__(self, message: str, suggestion: Optional[str] = None, original_error: Optional[Exception] = None):
        self.message = message
        self.suggestion = suggestion
        self.original_error = original_error
        super().__init__(self.format_message())

    def format_message(self) -> str:
        """Format error message with suggestion."""
        msg = self.message
        if self.suggestion:
            msg += f"\n\nSuggestion: {self.suggestion}"
        if self.original_error:
            msg += f"\n\nOriginal error: {str(self.original_error)}"
        return msg


class PlexConnectionError(PlexSubSetterError):
    """Raised when connection to Plex server fails."""

    def __init__(self, server_url: str = "", original_error: Optional[Exception] = None):
        message = f"Failed to connect to Plex server{': ' + server_url if server_url else ''}"
        suggestion = (
            "Check that:\n"
            "  1. Plex Media Server is running\n"
            "  2. Server URL is correct\n"
            "  3. Network connection is stable\n"
            "  4. Firewall is not blocking the connection"
        )
        super().__init__(message, suggestion, original_error)


class PlexAuthenticationError(PlexSubSetterError):
    """Raised when Plex authentication fails."""

    def __init__(self, original_error: Optional[Exception] = None):
        message = "Plex authentication failed"
        suggestion = (
            "Try:\n"
            "  1. Log out and log in again\n"
            "  2. Check your Plex account credentials\n"
            "  3. Verify your authentication token is valid"
        )
        super().__init__(message, suggestion, original_error)


# ==================== RETRY DECORATOR ====================

def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    Decorator to retry a function with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        backoff_factor: Multiplier for delay after each retry
        exceptions: Tuple of exception types to catch and retry
        on_retry: Optional callback function called on each retry (func, attempt, error)

    Example:
        @retry_with_backoff(max_attempts=3, initial_delay=1.0, exceptions=(ConnectionError,))
        def connect_to_server():
            # Connection logic here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            attempt = 1
            delay = initial_delay

            while attempt <= max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        # Last attempt failed, re-raise
                        logging.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise

                    # Log retry attempt
                    logging.warning(
                        f"{func.__name__} failed (attempt {attempt}/{max_attempts}). "
                        f"Retrying in {delay:.1f}s... Error: {e}"
                    )

                    # Call retry callback if provided
                    if on_retry:
                        try:
                            on_retry(func, attempt, e)
                        except Exception as callback_error:
                            logging.error(f"Retry callback failed: {callback_error}")

                    # Wait before retry
                    time.sleep(delay)

                    # Increase delay for next attempt
                    delay *= backoff_factor
                    attempt += 1

            # Should never reach here, but just in case
            raise RuntimeError(f"{func.__name__} exceeded max attempts without raising")

        return wrapper
    return decorator


# ==================== CRASH LOG SYSTEM ====================

class CrashReporter:
    """Handles crash reporting and error logging."""

    def __init__(self, crash_log_dir: str = "logs/crashes"):
        self.crash_log_dir = Path(crash_log_dir)
        self.crash_log_dir.mkdir(parents=True, exist_ok=True)

    def report_crash(self, error: Exception, context: Dict[str, Any] = None):
        """
        Report a crash with full traceback and context.

        Args:
            error: The exception that caused the crash
            context: Additional context information (e.g., current state, user action)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        crash_file = self.crash_log_dir / f"crash_{timestamp}.log"

        try:
            with open(crash_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write(f"PLEXSUBSETTER CRASH REPORT\n")
                f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")

                # Error information
                f.write(f"Error Type: {type(error).__name__}\n")
                f.write(f"Error Message: {str(error)}\n\n")

                # Context information
                if context:
                    f.write("Context Information:\n")
                    for key, value in context.items():
                        f.write(f"  {key}: {value}\n")
                    f.write("\n")

                # Full traceback
                f.write("Full Traceback:\n")
                f.write("-" * 80 + "\n")
                f.write(traceback.format_exc())
                f.write("-" * 80 + "\n\n")

                # System information
                f.write("System Information:\n")
                f.write(f"  Python Version: {os.sys.version}\n")
                f.write(f"  Platform: {os.sys.platform}\n")
                f.write(f"  Working Directory: {os.getcwd()}\n")

            logging.error(f"Crash report saved to: {crash_file}")
            return str(crash_file)

        except Exception as report_error:
            logging.error(f"Failed to write crash report: {report_error}")
            return None


# ==================== CONTEXT MANAGER FOR ERROR TRACKING ====================

class ErrorContext:
    """Context manager for tracking errors with additional context."""

    def __init__(self, operation: str, crash_reporter: Optional[CrashReporter] = None):
        self.operation = operation
        self.crash_reporter = crash_reporter
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        logging.debug(f"Starting: {self.operation}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time

        if exc_type is None:
            logging.debug(f"Completed: {self.operation} ({duration:.2f}s)")
            return True

        # Error occurred
        logging.error(f"Failed: {self.operation} after {duration:.2f}s - {exc_val}")

        # Report crash if reporter available
        if self.crash_reporter:
            context = {
                "operation": self.operation,
                "duration_seconds": duration,
                "error_type": exc_type.__name__
            }
            self.crash_reporter.report_crash(exc_val, context)

        return False  # Re-raise exception


# ==================== GLOBAL CRASH REPORTER INSTANCE ====================

# Initialize global crash reporter
_global_crash_reporter = CrashReporter()

def get_crash_reporter() -> CrashReporter:
    """Get the global crash reporter instance."""
    return _global_crash_reporter
