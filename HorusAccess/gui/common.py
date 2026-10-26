"""Shared widgets, key labels and modal helpers for the Tk windows."""

import customtkinter as ctk
from tkinter import TclError

try:
    from core.keys import canonical_key
    from core.ui_utils import default_font_family
except ImportError:  # Imported as part of the HorusAccess package (tests).
    from HorusAccess.core.keys import canonical_key
    from HorusAccess.core.ui_utils import default_font_family


KEYBOARD_LAYOUT = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
    ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
    ["A", "S", "D", "F", "G", "H", "J", "K", "L", "enter"],
    ["Z", "X", "C", "V", "B", "N", "M", "space", "up", "down"],
    ["left", "right", "left_click", "right_click"],
]

_KEY_LABELS = {
    "enter": "ENTER",
    "space": "SPACE",
    "up": "UP",
    "down": "DOWN",
    "left": "LEFT",
    "right": "RIGHT",
    "left_click": "L. CLICK",
    "right_click": "R. CLICK",
}


def key_label(key):
    """Display spelling used by the key pickers and the review window."""
    name = canonical_key(key)
    if name is None:
        return str(key).upper()
    return _KEY_LABELS.get(name, name.upper())


KEY_CHOICES = list(dict.fromkeys(
    canonical_key(key) for row in KEYBOARD_LAYOUT for key in row
))
KEY_OPTION_LABELS = [key_label(key) for key in KEY_CHOICES]
KEY_BY_LABEL = {key_label(key): key for key in KEY_CHOICES}


def ui_font(**kwargs):
    """CTkFont που χρησιμοποιεί πάντα οικογένεια γραμματοσειρών διαθέσιμη στο τρέχον OS."""
    return ctk.CTkFont(family=default_font_family(), **kwargs)


def grab_modal(window):
    """Κάνει το ``window`` modal αφού ο window manager το εμφανίσει.

    Το ``grab_set()`` αμέσως μετά τη δημιουργία ενός ``Toplevel`` μπορεί να
    αποτύχει στο X11/XWayland με ``grab failed: window not viewable``, γιατί το
    παράθυρο υπάρχει αλλά δεν έχει χαρτογραφηθεί ακόμη. Περιμένουμε πρώτα να
    γίνει ορατό, ώστε το grab να είναι αξιόπιστο σε όλες τις πλατφόρμες.
    """
    try:
        window.wait_visibility()
        window.grab_set()
    except TclError:
        # Το παράθυρο έκλεισε όσο περίμενε· δεν υπάρχει τίποτα να κάνουμε.
        pass
