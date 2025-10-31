#!/usr/bin/env python3
"""
PlexSubSetter - Mass Subtitle Finder and Setter for Plex
Main application entry point with modular architecture.
"""

import customtkinter as ctk
import logging

# Import UI components
from ui.login_frame import LoginFrame
from ui.server_selection_frame import ServerSelectionFrame
from ui.main_app_frame import MainAppFrame

# Import utilities
from utils.constants import __version__, __author__, __repo__
from utils.logging_config import setup_logging


# Set appearance and theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Initialize logging
current_log_file = setup_logging()


class PlexSubSetterApp(ctk.CTk):
    """Main application class."""

    def __init__(self):
        super().__init__()

        self.title("PlexSubSetter")

        # Start with small default window (will be resized when showing frames)
        self.geometry("500x600")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.current_frame = None
        self.account = None
        self.plex = None
        self.is_closing = False

        # Handle window close event
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Show login frame
        self.show_login()

    def on_closing(self):
        """Handle application closing."""
        self.is_closing = True

        # Clean up current frame properly
        if self.current_frame:
            try:
                self.current_frame.destroy()
            except:
                pass

        # Destroy the window
        try:
            self.quit()
            self.destroy()
        except:
            pass

    def resize_and_center(self, width, height):
        """Resize window and center it on screen."""
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def show_login(self):
        """Show login frame."""
        if self.is_closing:
            return

        if self.current_frame:
            try:
                self.current_frame.destroy()
            except:
                pass

        # Resize for login (small window)
        self.minsize(400, 500)
        self.resize_and_center(500, 600)

        self.current_frame = LoginFrame(self, self.on_login_success)
        self.current_frame.grid(row=0, column=0, sticky="nsew")

    def on_login_success(self, account):
        """Handle successful login."""
        if self.is_closing:
            return
        logging.info(f"User '{account.username}' logged in successfully")
        self.account = account
        self.show_server_selection()

    def show_server_selection(self):
        """Show server selection frame."""
        if self.is_closing:
            return

        if self.current_frame:
            try:
                self.current_frame.destroy()
            except:
                pass

        # Resize for server selection (medium window)
        self.minsize(600, 500)
        self.resize_and_center(700, 600)

        self.current_frame = ServerSelectionFrame(self, self.account,
                                                  self.on_server_selected,
                                                  self.show_server_selection)
        self.current_frame.grid(row=0, column=0, sticky="nsew")

    def on_server_selected(self, plex):
        """Handle server selection."""
        if self.is_closing:
            return
        self.plex = plex
        self.show_main_app()

    def show_main_app(self):
        """Show main application."""
        if self.is_closing:
            return

        if self.current_frame:
            try:
                self.current_frame.destroy()
            except:
                pass

        # Resize for main app (large window)
        self.minsize(1000, 750)
        self.resize_and_center(1200, 850)

        self.current_frame = MainAppFrame(self, self.plex, self.show_server_selection, current_log_file)
        self.current_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)


def main():
    """Main entry point."""
    app = PlexSubSetterApp()
    app.mainloop()


if __name__ == '__main__':
    main()
