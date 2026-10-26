"""Magnetic cursor targets for the face-tracking loop.

The mixin only needs a live Tk root, so it can be used by the main application
and by a plain ``CTk`` window in live probes. It discovers the controls of the
window the user is actually interacting with and returns their centres in the
same coordinate space as ``core.input_backend``.
"""

import time
from tkinter import TclError

import customtkinter as ctk

try:
    from core.input_backend import screen_origin
    from core.ui_utils import snap_to_nearest
except ImportError:  # Imported as part of the HorusAccess package (tests).
    from HorusAccess.core.input_backend import screen_origin
    from HorusAccess.core.ui_utils import snap_to_nearest


# Η ιχνηλάτηση κεφαλιού δεν σταματά ακριβώς πάνω σε ένα μικρό κουμπί. Όταν ο
# εικονικός δείκτης βρίσκεται τόσα pixel από το κέντρο ενός χειριστηρίου, το
# warp προσγειώνεται στο κέντρο του, ώστε το πάτημα να είναι εύκολο.
SNAP_DISTANCE = 45
# Η γεωμετρία αλλάζει μόνο όταν αλλάζει η διάταξη· μια πλήρης σάρωση των
# widgets σε κάθε καρέ θα ήταν σπατάλη.
SNAP_CACHE_SECONDS = 0.5

# Χειριστήρια στα οποία «κολλάει» ο δείκτης.
SNAP_WIDGET_TYPES = (
    ctk.CTkButton,
    ctk.CTkSlider,
    ctk.CTkSwitch,
    ctk.CTkCheckBox,
    ctk.CTkOptionMenu,
)


class SnapCursorMixin:
    """Target discovery and snapping for an app that owns ``_snap_cache``."""

    def __init__(self, *args, **kwargs):
        # Cooperative initialisation: the concrete class inherits from CTk after
        # this mixin, so the normal Tk setup still has to run.
        super().__init__(*args, **kwargs)

    def _iter_snap_widgets(self, widget):
        """Βαθιά αναζήτηση όλων των διαδραστικών χειριστηρίων."""
        for child in widget.winfo_children():
            if isinstance(child, SNAP_WIDGET_TYPES):
                yield child
            yield from self._iter_snap_widgets(child)

    def _active_toplevel(self):
        """Το παράθυρο με το οποίο αλληλεπιδρά ο χρήστης, ή ``None``.

        Το ``winfo_viewable()`` σημαίνει «χαρτογραφημένο», όχι «μπροστά»: ένα
        παράθυρο σε άλλο workspace ή πίσω από ένα modal παραμένει viewable. Γι'
        αυτό πρώτα ελέγχεται αν η εφαρμογή έχει την εστίαση και μετά επιλέγεται
        το ανώτερο ορατό toplevel της, ώστε να μη μαζεύονται στόχοι από κρυφά
        ή καλυμμένα χειριστήρια.
        """
        try:
            grabbed = self.grab_current()
        except TclError:
            grabbed = None
        if grabbed:
            try:
                return grabbed.winfo_toplevel()
            except TclError:
                return None

        focused = None
        for getter in (self.focus_displayof, self.focus_get):
            try:
                focused = getter()
            except (KeyError, TclError):
                focused = None
            if focused is not None:
                break
        if not focused:
            # Καμία εστίαση σε αυτή την εφαρμογή (π.χ. τοποθετήθηκε άλλο
            # παράθυρο μπροστά ή αλλάξαμε workspace).
            return None

        topmost = None
        try:
            for path in self.tk.call("wm", "stackorder", self._w):
                candidate = self.nametowidget(path)
                if candidate.winfo_viewable():
                    topmost = candidate
        except (KeyError, TclError):
            topmost = None
        if topmost is not None:
            return topmost
        try:
            return focused.winfo_toplevel()
        except TclError:
            return None

    def _widget_is_exposed(self, widget, root_x, root_y):
        """Whether the widget is the topmost thing at its centre."""
        try:
            top = self.winfo_containing(root_x, root_y)
        except (KeyError, TclError):
            return False
        if top is None:
            # Tk cannot tell (e.g. the point is outside every Tk window); keep
            # the target rather than silently dropping a real control.
            return True
        path = str(widget)
        actual = str(top)
        return actual == path or actual.startswith(f"{path}.")

    def _snap_targets(self):
        """Κέντρα των ορατών χειριστηρίων, στις συντεταγμένες του δείκτη."""
        now = time.monotonic()
        cached_at, targets = self._snap_cache
        if now - cached_at < SNAP_CACHE_SECONDS:
            return targets

        active = self._active_toplevel()
        if active is None:
            self._snap_cache = (now, [])
            return []

        origin_x, origin_y = screen_origin()
        targets = []
        for widget in self._iter_snap_widgets(self):
            try:
                if widget.winfo_toplevel()._w != active._w:
                    continue
                if not widget.winfo_viewable():
                    continue
                width, height = widget.winfo_width(), widget.winfo_height()
                if width <= 1 or height <= 1:
                    continue
                root_x = widget.winfo_rootx() + width // 2
                root_y = widget.winfo_rooty() + height // 2
                if not self._widget_is_exposed(widget, root_x, root_y):
                    continue
                targets.append((root_x - origin_x, root_y - origin_y))
            except (KeyError, TclError):
                # Ένα widget που καταστρέφεται όσο το σαρώνουμε δεν πρέπει να
                # σταματήσει τη σάρωση των υπόλοιπων.
                continue
        self._snap_cache = (now, targets)
        return targets

    def _snap_cursor(self, x, y):
        return snap_to_nearest(x, y, self._snap_targets(), SNAP_DISTANCE)
