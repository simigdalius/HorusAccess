import json
import os
import queue
import sys
import threading
import time
import warnings
from tkinter import messagebox

import cv2
import customtkinter as ctk
import mediapipe as mp
import numpy as np
import ollama
from PIL import Image, ImageTk

# Ο φάκελος HorusAccess πρέπει να είναι στο sys.path πριν από τα imports των
# core/database, ώστε να δουλεύει και το `python HorusAccess/gui/main.py`.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ai_mappings import (
    build_request,
    ensure_left_click,
    is_2d_platformer,
    validate_mappings,
)
from core.game_detector import detect_installed_games
from core.game_images import download_game_image
from core.gestures import (
    GESTURES,
    HeadPoseTracker,
    canonical_motion,
    compute_facial_metrics,
    default_threshold,
    default_thresholds,
    display_name,
    is_gesture_active,
    short_display_name,
)
from core.input_backend import (
    disable_failsafe,
    key_down,
    key_up,
    mouse_activity_count,
    mouse_move,
    mouse_position,
    open_webcam,
    screen_size,
)
from core.keys import canonical_key
from database.db_manager import DBManager
from gui.common import (
    KEYBOARD_LAYOUT,
    KEY_BY_LABEL,
    KEY_OPTION_LABELS,
    grab_modal,
    key_label,
    ui_font,
)
from gui.snapping import SnapCursorMixin


# Πόσο καιρό η χειροκίνητη κίνηση του ποντικιού αναστέλλει την κίνηση από το
# κεφάλι. Κάθε νέα φυσική κίνηση ανανεώνει το διάστημα.
MOUSE_OVERRIDE_SECONDS = 3.0


# horus AI
disable_failsafe()
class AutonomousGameSelectorWindow(ctk.CTkToplevel):
    """Παράθυρο πλέγματος που εμφανίζει τα πραγματικά εγκατεστημένα παιχνίδια του PC."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self._dialog = None
        self._closed = False
        self._ui_queue = queue.Queue()
        self._image_labels = {}
        self._image_jobs = []
        self._pending_cards = []
        self._analysis_in_progress = False

        self.title("Horus AI - Αυτόνομη Επιλογή Εγκατεστημένων Παιχνιδιών")
        self.geometry("950x700")
        self.configure(fg_color="#111215")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Η ανίχνευση τρέχει σε worker thread, ώστε το παράθυρο να ζωγραφιστεί
        # αμέσως και το Tk event loop να μη «παγώσει» όσο διαρκεί η σάρωση.
        self.games = []
        self._build_ui()
        # Το grab μπαίνει μετά το χτίσιμο του UI: το ``wait_visibility()``
        # περιμένει χαρτογράφηση και δεν πρέπει να προλάβει κενό παράθυρο.
        grab_modal(self)
        self.after(50, self._start_detection)
        self.after(50, self._process_ui_queue)


    def _on_close(self):
        """Κλείνει το παράθυρο και τυχόν παιδικό dialog επιβεβαίωσης."""
        self._closed = True
        if self._dialog is not None:
            try:
                self._dialog.grab_release()
                self._dialog.destroy()
            except Exception:
                pass
            self._dialog = None
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


    def _post(self, callback):
        """Ουρά για την ασφαλή μεταφορά αποτελεσμάτων από worker στο Tk thread."""
        if not self._closed:
            self._ui_queue.put(callback)


    def _process_ui_queue(self):
        """Εκτελεί στην κύρια thread ό,τι έστειλαν οι workers."""
        if self._closed:
            return

        while True:
            try:
                callback = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception as e:
                print(f"⚠️ Σφάλμα κατά την ενημέρωση του παραθύρου επιλογής: {e}")

        if not self._closed:
            self.after(50, self._process_ui_queue)


    def _start_detection(self):
        threading.Thread(target=self._detect_games_worker, daemon=True).start()


    def _detect_games_worker(self):
        games = self.detect_installed_games()
        self._post(lambda: self._on_games_loaded(games))


    def detect_installed_games(self):
        """Ανιχνεύει παιχνίδια από Steam, Epic, GOG και τον φάκελο εφαρμογών.

        Η λογική ζει στο core/game_detector.py ώστε να είναι κοινή για
        Windows, Linux και macOS."""
        try:
            return detect_installed_games()
        except Exception as e:
            print(f"⚠️ Αποτυχία ανίχνευσης εγκατεστημένων παιχνιδιών: {e}")
            return []


    def _on_games_loaded(self, games):
        self.games = games
        if self.loading_label is not None:
            self.loading_label.destroy()
            self.loading_label = None

        if not self.games:
            ctk.CTkLabel(
                self.grid_frame,
                text="⚠️ Δεν βρέθηκαν εγκατεστημένα παιχνίδια.",
                font=ui_font(size=16),
                text_color="#6c7281",
            ).grid(row=0, column=0, columnspan=3, pady=60)
            return

        # Οι κάρτες προστίθενται σε μικρές ομάδες, ώστε ακόμη και μια μεγάλη
        # βιβλιοθήκη να μην μπλοκάρει το πρώτο repaint.
        self._pending_cards = list(enumerate(self.games))
        self._add_pending_cards()


    def _add_pending_cards(self):
        if self._closed:
            return

        for _ in range(6):
            if not self._pending_cards:
                break
            index, game = self._pending_cards.pop(0)
            self._add_game_card(index, game)

        if self._pending_cards:
            self.after(1, self._add_pending_cards)
            return

        self._image_jobs = list(enumerate(self.games))
        threading.Thread(target=self._load_images_worker, daemon=True).start()


    def _load_images_worker(self):
        """Κατεβάζει τις εικόνες μία-μία και τις στέλνει στο Tk thread."""
        for index, game in self._image_jobs:
            if self._closed:
                return
            image = download_game_image(
                game_title=game.get('title', ''),
                image_url=game.get('image_url'),
                size=(220, 120),
            )
            if image is not None:
                self._post(lambda i=index, img=image: self._set_game_image(i, img))


    def _set_game_image(self, index, pil_image):
        img_label = self._image_labels.get(index)
        if img_label is None:
            return
        try:
            if not img_label.winfo_exists():
                return
        except Exception:
            return

        ctk_img = ctk.CTkImage(
            light_image=pil_image, dark_image=pil_image, size=(220, 120)
        )
        img_label.configure(image=ctk_img, text="")
        img_label.image = ctk_img  # Garbage collection reference


    def _add_game_card(self, index, game):
        row = index // 3
        col = index % 3

        # Κάρτα Παιχνιδιού
        card = ctk.CTkFrame(
            self.grid_frame,
            fg_color="#1f2128",
            corner_radius=12,
            border_color="#2b2d35",
            border_width=1,
        )
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

        # 1. Εικόνα: placeholder τώρα, αντικαθίσταται όταν φτάσει το download.
        img_label = ctk.CTkLabel(card, text="🎮", font=ctk.CTkFont(size=45))
        img_label.pack(pady=(20, 10))
        self._image_labels[index] = img_label

        # 2. Τίτλος Παιχνιδιού
        ctk.CTkLabel(
            card,
            text=game.get('title', 'Άγνωστο Παιχνίδι'),
            font=ui_font(size=15, weight="bold"),
            text_color="#ffffff",
            wraplength=200,
        ).pack(pady=(5, 2), padx=8)

        # 3. Badge Πλατφόρμας
        ctk.CTkLabel(
            card,
            text=f"• {game.get('platform', 'PC')} •",
            font=ui_font(size=12, weight="bold"),
            text_color="#00ffaa",
        ).pack(pady=(0, 10))

        # 4. Μεγάλο Κουμπί Επιλογής (Easy Target)
        btn = ctk.CTkButton(
            card,
            text="🎯 Ανάλυση & Επιλογή",
            font=ui_font(size=14, weight="bold"),
            fg_color="#00f0ff",
            text_color="#111215",
            hover_color="#00ffaa",
            height=48,  # Αυξημένο ύψος για εύκολη επιλογή
            corner_radius=8,
            command=lambda g=game: self.select_game(g),
        )
        btn.pack(pady=(0, 15), padx=12, fill="x")


    def _build_ui(self):
        # 1. Εμφάνιση Τίτλου
        ctk.CTkLabel(
            self, 
            text="🤖 ΕΓΚΑΤΕΣΤΗΜΕΝΑ ΠΑΙΧΝΙΔΙΑ (Horus AI)", 
            font=ui_font(size=24, weight="bold"), 
            text_color="#00f0ff"
        ).pack(pady=(20, 10))

        # 2. Scrollable Frame για το πλέγμα των παιχνιδιών
        self.grid_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill="both", expand=True, padx=20, pady=10)
        self.grid_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="col")

        self.loading_label = ctk.CTkLabel(
            self.grid_frame,
            text="⏳ Ανίχνευση εγκατεστημένων παιχνιδιών...",
            font=ui_font(size=16),
            text_color="#6c7281",
        )
        self.loading_label.grid(row=0, column=0, columnspan=3, pady=60)

        # 3. ΜΕΓΑΛΟ ΚΟΥΜΠΙ ΚΛΕΙΣΙΜΟΥ (Large Close Target)
        self.close_btn = ctk.CTkButton(
            self,
            text="❌ ΚΛΕΙΣΙΜΟ",
            font=ui_font(size=20, weight="bold"),
            height=55,                  # Μεγάλο ύψος για εύκολο στόχο
            fg_color="#c0392b",
            hover_color="#e74c3c",
            corner_radius=12,
            command=self._on_close        # Κλείνει το παράθυρο/frame
        )
        self.close_btn.pack(pady=15, padx=30, fill="x")

    
    def select_game(self, game):
        if self._analysis_in_progress:
            print("⏳ Η ανάλυση του Horus AI είναι ήδη σε εξέλιξη.")
            return

        self._analysis_in_progress = True
        print(f"🤖 [Horus AI] Αναλύονται οι λειτουργίες για: {game['title']}...")
        
        prompt, allowed_keys, fallback = build_request(game['title'])

        threading.Thread(
            target=self._analyse_game_worker,
            args=(game, prompt, allowed_keys, fallback),
            daemon=True,
        ).start()

    def _analyse_game_worker(self, game, prompt, allowed_keys, fallback):
        """Καλεί το Ollama εκτός του Tk thread και επιστρέφει το αποτέλεσμα."""
        mappings = []
        try:
            # Κλήση στο Ollama LLM
            try:
                response = ollama.chat(
                    model='llama3.2:1b',
                    messages=[{'role': 'user', 'content': prompt}],
                    format='json'
                )
            except Exception:
                response = ollama.chat(
                    model='llama3.2',
                    messages=[{'role': 'user', 'content': prompt}],
                    format='json'
                )
            
            raw_content = response['message']['content'].strip()
            
            # Απευθείας parsing καθώς το format='json' του Ollama εγγυάται καθαρό JSON
            result = json.loads(raw_content)
            
            # Fallback αν το μοντέλο επιστρέψει λίστα αντί για dictionary
            if isinstance(result, list):
                items = result
            elif isinstance(result, dict):
                items = result.get("mappings", [])
            else:
                items = []

            mappings = validate_mappings(items, allowed_keys)
            print(f"✅ Δημιουργήθηκαν {len(mappings)} έγκυρα mappings για το {game['title']}")

        except Exception as e:
            print(f"⚠️ Σφάλμα απόκρισης Ollama: {e}")

        self._post(lambda: self._on_analysis_complete(game, mappings, fallback))

    def _on_analysis_complete(self, game, mappings, fallback):
        self._analysis_in_progress = False
        if self._closed:
            return

        if not mappings:
            print("⚠️ Το LLM δεν επέστρεψε mappings. Εφαρμογή έξυπνου Fallback...")
            mappings = fallback

        if not is_2d_platformer(game.get('title')):
            mappings = ensure_left_click(mappings)

        # 1. Εύρεση του πρώτου κενού προφίλ (1 έως 5)
        target_profile = None
        if hasattr(self.parent, 'db'):
            for p_id in range(1, 6):
                existing = self.parent.db.get_mappings(p_id)
                if not existing:
                    target_profile = p_id
                    break

        if target_profile is None:
            messagebox.showwarning(
                "Δεν υπάρχει κενό προφίλ",
                "Και τα 5 προφίλ έχουν ήδη κινήσεις.\n\n"
                "Άνοιξε «Εμφάνιση Καταχωρημένων» και διάγραψε κινήσεις από ένα "
                "προφίλ πριν χρησιμοποιήσεις το Horus AI.",
                parent=self,
            )
            return

        # 2. Εμφάνιση παραθύρου επιβεβαίωσης
        self.show_confirmation_dialog(game['title'], mappings, target_profile)
    
    def show_confirmation_dialog(self, game_title, mappings, target_profile):
        """Εμφανίζει παράθυρο με τις προτάσεις του Horus AI και περιμένει επιβεβαίωση (OK)."""
        dialog = ctk.CTkToplevel(self)
        self._dialog = dialog
        dialog.title("Πρόταση Horus AI")
        dialog.geometry("550x480")
        dialog.configure(fg_color="#111215")
        dialog.attributes("-topmost", True)

        def close_dialog():
            self._dialog = None
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", close_dialog)

        # Τίτλος
        ctk.CTkLabel(
            dialog, 
            text="🤖 ΤΟ HORUS AI ΠΡΟΤΕΙΝΕΙ:", 
            font=ui_font(size=20, weight="bold"), 
            text_color="#00f0ff"
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            dialog, 
            text=f"Παιχνίδι: {game_title}\nΘα γίνει αποθήκευση στο Προφίλ {target_profile}", 
            font=ui_font(size=14, weight="bold"), 
            text_color="#00ffaa"
        ).pack(pady=(0, 15))

        # Λίστα προτεινόμενων controls
        scroll_frame = ctk.CTkScrollableFrame(dialog, fg_color="#1f2128", height=220)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=5)

        for m in mappings:
            motion = m.get("motion", "?")
            key = str(m.get("key", "")).upper()
            description = m.get("description", "")
            row_str = f"• {motion} ➔ [{key}] ({description})"
            ctk.CTkLabel(
                scroll_frame, 
                text=row_str, 
                font=ui_font(size=14), 
                text_color="#ffffff",
                anchor="w"
            ).pack(fill="x", pady=4, padx=10)

        # Συνάρτηση που εκτελείται όταν πατηθεί το OK
        def confirm_and_save():
            if hasattr(self.parent, 'db'):
                # 1. Αποθήκευση των mappings
                for item in mappings:
                    motion = item.get("motion")
                    key = item.get("key")
                    if not motion or not key:
                        continue
                    self.parent.db.save_mapping(
                        profile_id=target_profile,
                        action=motion,
                        mapped_key=key,
                        default_threshold=default_threshold(motion),
                    )
                
                # 2. Αποθήκευση του ονόματος της εφαρμογής για το προφίλ
                if game_title:
                    self.parent.db.update_profile_name(target_profile, game_title)
                
                print(f"💾 Επιτυχής αποθήκευση για την εφαρμογή '{game_title}' στο Προφίλ {target_profile}!")
                
                # 3. Ενημέρωση του UI της εφαρμογής
                if hasattr(self.parent, 'profile_selector'):
                    self.parent.profile_selector.set(str(target_profile))
                if hasattr(self.parent, 'change_profile'):
                    self.parent.change_profile(str(target_profile))

            close_dialog()
            self.grab_release()
            self.destroy()

        # Κουμπί OK
        btn_ok = ctk.CTkButton(
            dialog,
            text="OK (Αποδοχή & Αποθήκευση)",
            font=ui_font(size=16, weight="bold"),
            height=45,
            fg_color="#00ffaa",
            text_color="#111215",
            hover_color="#00f0ff",
            command=confirm_and_save
        )
        btn_ok.pack(pady=20, padx=20, fill="x")

        # Το grab γίνεται αφού χτιστεί όλο το περιεχόμενο, ώστε το
        # ``wait_visibility()`` να μη δεσμεύσει ένα ακόμη κενό παράθυρο.
        grab_modal(dialog)



class ProfileReviewWindow(ctk.CTkToplevel):
    def __init__(self, parent, current_profile_id, db):
        super().__init__(parent)
        
        self.parent = parent
        self.profile_id = current_profile_id
        self.db = db

        self.title(f"Εμφάνιση & Επεξεργασία Καταχωρημένων (Προφίλ {self.profile_id})")
        self.geometry("880x600")
        self.attributes("-topmost", True)

        self.row_widgets = {} 
        self.is_locked = False

        self._build_ui()
        self.load_data()

    def _build_ui(self):
        # 1. Αναζήτηση αν υπάρχει όνομα παιχνιδιού/εφαρμογής για το προφίλ
        profile_name = f"Προφίλ {self.profile_id}"
        if hasattr(self.db, 'get_profile_name'):
            game_name = self.db.get_profile_name(self.profile_id)
            if game_name:
                profile_name = f"Προφίλ {self.profile_id} - {game_name}"
        elif hasattr(self.parent, 'profile_games') and self.profile_id in self.parent.profile_games:
            profile_name = f"Προφίλ {self.profile_id} - {self.parent.profile_games[self.profile_id]}"

        # 2. Εμφάνιση Τίτλου
        ctk.CTkLabel(
            self, 
            text=f"Διαχείριση Κινήσεων\n({profile_name})", 
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#00f0ff"
        ).pack(pady=15)

        # 3. Scrollable Frame για τις κινήσεις
        self.scroll_frame = ctk.CTkScrollableFrame(self, width=720, height=380)
        self.scroll_frame.pack(pady=10, padx=20, fill="both", expand=True)

        # 4. Αποθήκευση / κλείδωμα των αλλαγών
        self.btn_lock = ctk.CTkButton(
            self,
            text="💾 Αποθήκευση & Κλείδωμα",
            font=ctk.CTkFont(size=17, weight="bold"),
            height=44,
            fg_color="#27ae60",
            hover_color="#2ecc71",
            corner_radius=10,
            command=self.save_and_lock
        )
        self.btn_lock.pack(pady=(8, 6), padx=30, fill="x")

        # 5. ΜΕΓΑΛΟ ΚΟΥΜΠΙ ΚΛΕΙΣΙΜΟΥ (Large Close Target)
        self.close_btn = ctk.CTkButton(
            self,
            text="❌ ΚΛΕΙΣΙΜΟ",
            font=ctk.CTkFont(size=20, weight="bold"),
            height=50,                  # Μεγάλο ύψος για εύκολο στόχο
            fg_color="#c0392b",
            hover_color="#e74c3c",
            corner_radius=12,
            command=self.destroy        # Κλείνει το παράθυρο/frame
        )
        self.close_btn.pack(pady=(0, 12), padx=30, fill="x")

    

    def load_data(self):
        """Φορτώνει τα mappings σε 4 στήλες:
        Είδος Κίνησης | Πλήκτρο | Όριο | Ενέργειες
        """
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.row_widgets.clear()

        mappings = self.db.get_mappings(self.profile_id)

        if not mappings:
            ctk.CTkLabel(
                self.scroll_frame,
                text="⚠️ Δεν υπάρχουν καταχωρημένες κινήσεις για αυτό το προφίλ.",
                font=ui_font(size=14),
                text_color="#6c7281"
            ).pack(pady=40)
            self._apply_lock_state()
            return

        # Header 4 Στηλών — ίδιες θέσεις/βάρη με τις γραμμές.
        header_frame = ctk.CTkFrame(self.scroll_frame, fg_color="#1f2128", height=35, corner_radius=6)
        header_frame.pack(fill="x", pady=(0, 8), padx=5)

        header_frame.grid_columnconfigure(0, weight=4)  # Είδος Κίνησης
        header_frame.grid_columnconfigure(1, weight=2)  # Πλήκτρο
        header_frame.grid_columnconfigure(2, weight=2)  # Όριο
        header_frame.grid_columnconfigure(3, weight=2)  # Ενέργειες

        ctk.CTkLabel(header_frame, text="Είδος Κίνησης", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a0a5b5").grid(row=0, column=0, sticky="w", padx=12, pady=5)
        ctk.CTkLabel(header_frame, text="Πλήκτρο", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a0a5b5").grid(row=0, column=1, sticky="w", padx=8, pady=5)
        ctk.CTkLabel(header_frame, text="Όριο (> / <)", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a0a5b5").grid(row=0, column=2, sticky="w", padx=8, pady=5)
        ctk.CTkLabel(header_frame, text="Ενέργειες", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a0a5b5").grid(row=0, column=3, padx=8, pady=5)

        # Εγγραφές
        for item in mappings:
            m_id, motion, key, threshold = item

            row = ctk.CTkFrame(self.scroll_frame, fg_color="#181a20", corner_radius=8)
            row.pack(fill="x", pady=3, padx=5)

            row.grid_columnconfigure(0, weight=4)
            row.grid_columnconfigure(1, weight=2)
            row.grid_columnconfigure(2, weight=2)
            row.grid_columnconfigure(3, weight=2)

            default = default_threshold(motion)
            if threshold is None:
                threshold = default if default is not None else 0.05

            # 1. Είδος Κίνησης
            ctk.CTkLabel(
                row, text=display_name(motion),
                font=ctk.CTkFont(size=13, weight="bold"), text_color="#ffffff"
            ).grid(row=0, column=0, sticky="w", padx=12, pady=6)

            # 2. Πλήκτρο
            current_label = key_label(key)
            key_values = list(KEY_OPTION_LABELS)
            if current_label not in key_values:
                key_values.append(current_label)
            key_dropdown = ctk.CTkOptionMenu(
                row,
                values=key_values,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#00f0ff", text_color="#111215",
                button_color="#00b8c4", button_hover_color="#00f0ff",
                dropdown_fg_color="#1f2128", dropdown_text_color="#ffffff",
                width=110, height=28, corner_radius=5,
            )
            key_dropdown.set(current_label)
            key_dropdown.grid(row=0, column=1, sticky="w", padx=8, pady=6)

            # 3. Όριο
            thresh_entry = ctk.CTkEntry(
                row,
                width=90, height=28,
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color="#111215", border_color="#262932",
                placeholder_text=f"{default:.3f}" if default is not None else "0.050",
            )
            thresh_entry.insert(0, f"{float(threshold):.3f}")
            thresh_entry.grid(row=0, column=2, sticky="w", padx=8, pady=6)

            # 4. Ενέργειες
            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.grid(row=0, column=3, padx=8, pady=4)

            edit_btn = ctk.CTkButton(
                actions, text="✏️",
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#f39c12", hover_color="#f1c40f", text_color="#111215",
                width=32, height=26, corner_radius=5,
                command=lambda mid=m_id: self.enable_edit(mid)
            )
            edit_btn.pack(side="left", padx=(0, 4))

            del_btn = ctk.CTkButton(
                actions, text="🗑️",
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#ff4757", hover_color="#ff6b81", text_color="#ffffff",
                width=32, height=26, corner_radius=5,
                command=lambda mid=m_id: self.delete_entry(mid)
            )
            del_btn.pack(side="left")

            self.row_widgets[m_id] = {
                "key_dropdown": key_dropdown,
                "thresh_entry": thresh_entry,
                "btn_edit": edit_btn,
                "btn_delete": del_btn,
            }

        self._apply_lock_state()

    def _apply_lock_state(self):
        """Ενεργοποιεί ή κλειδώνει όλα τα widgets των γραμμών."""
        state = "disabled" if self.is_locked else "normal"
        for widgets in self.row_widgets.values():
            widgets["key_dropdown"].configure(state=state)
            widgets["thresh_entry"].configure(state=state)
            widgets["btn_edit"].configure(state=state)
            widgets["btn_delete"].configure(state=state)

        if not hasattr(self, "btn_lock"):
            return
        if self.is_locked:
            self.btn_lock.configure(
                text="🔓 Ξεκλείδωμα",
                fg_color="#c0392b",
                hover_color="#e74c3c",
            )
        else:
            self.btn_lock.configure(
                text="💾 Αποθήκευση & Κλείδωμα",
                fg_color="#27ae60",
                hover_color="#2ecc71",
            )

    def enable_edit(self, mapping_id):
        if self.is_locked:
            return

        widgets = self.row_widgets.get(mapping_id)
        if widgets is None:
            return
        widgets["key_dropdown"].configure(state="normal")
        widgets["thresh_entry"].configure(state="normal")
        widgets["thresh_entry"].focus_set()

    def delete_entry(self, mapping_id):
        if self.is_locked:
            return

        current = {row[0]: row[2] for row in self.db.get_mappings(self.profile_id)}
        remaining = [key for mid, key in current.items() if mid != mapping_id]
        deleting_click = canonical_key(current.get(mapping_id)) == "left_click"
        if deleting_click and not any(canonical_key(key) == "left_click" for key in remaining):
            messagebox.showwarning(
                "Απαιτείται Κλικ",
                "Το αριστερό κλικ (L. CLICK) πρέπει να έχει πάντα μια κίνηση.\n\n"
                "Όρισε πρώτα άλλη κίνηση για το L. CLICK.",
                parent=self,
            )
            return

        self.db.delete_mapping(mapping_id)
        print(f"Διαγράφηκε η κίνηση με ID {mapping_id}")
        self.load_data()
        self.parent.refresh_active_mappings()

    def save_and_lock(self):
        if self.is_locked:
            self.is_locked = False
            self._apply_lock_state()
            return

        # Ελέγχουμε πρώτα όλες τις γραμμές, ώστε ένα λάθος να μην αφήσει τη
        # βάση μισοενημερωμένη.
        current = {row[0]: row[2] for row in self.db.get_mappings(self.profile_id)}
        updates = []
        for m_id, widgets in self.row_widgets.items():
            label = widgets["key_dropdown"].get()
            new_key = KEY_BY_LABEL.get(label, canonical_key(label))
            if not new_key:
                messagebox.showwarning(
                    "Μη έγκυρο πλήκτρο",
                    f"Το πλήκτρο «{label}» δεν αναγνωρίζεται.",
                    parent=self,
                )
                return

            raw_threshold = widgets["thresh_entry"].get().strip().replace(",", ".")
            try:
                new_thresh = float(raw_threshold)
            except ValueError:
                messagebox.showwarning(
                    "Μη έγκυρο όριο",
                    f"Το όριο «{raw_threshold}» δεν είναι αριθμός.",
                    parent=self,
                )
                return
            if not 0.0 < new_thresh <= 1.0:
                messagebox.showwarning(
                    "Μη έγκυρο όριο",
                    "Το όριο πρέπει να είναι μεταξύ 0 και 1 (π.χ. 0.105).",
                    parent=self,
                )
                return

            updates.append((m_id, new_key, new_thresh))

        pending = dict(current)
        for m_id, new_key, _ in updates:
            pending[m_id] = new_key
        if (
            any(canonical_key(key) == "left_click" for key in current.values())
            and not any(canonical_key(key) == "left_click" for key in pending.values())
        ):
            messagebox.showwarning(
                "Απαιτείται Κλικ",
                "Το αριστερό κλικ (L. CLICK) πρέπει να έχει πάντα μια κίνηση.\n\n"
                "Όρισε πρώτα άλλη κίνηση για το L. CLICK.",
                parent=self,
            )
            return

        for m_id, new_key, new_thresh in updates:
            self.db.update_mapping(m_id, new_key, new_thresh)

        self.is_locked = True
        self._apply_lock_state()
        self.parent.refresh_active_mappings()
        print("Το προφίλ αποθηκεύτηκε και κλειδώθηκε.")


class MotionInputWindow(ctk.CTkToplevel):
    def __init__(self, parent, current_profile_id, db):
        super().__init__(parent)
        self.parent = parent
        self.profile_id = current_profile_id
        self.db = db

        self.selected_motion = None
        self.selected_key = None

        self.motion_buttons = {}
        self.key_buttons = {}

        self.BG_MAIN = "#111215"          
        self.BG_WIDGETS = "#1f2128"       
        self.MODERN_CYAN = "#00f0ff"      
        self.MODERN_GREEN = "#00ffaa"     
        self.TEXT_WHITE = "#ffffff"
        self.BORDER_DEFAULT = "#262932"

        self.title("Εισαγωγή Κίνησης - HorusAccess")
        self.geometry("1050x680")
        self.configure(fg_color=self.BG_MAIN)
        self.attributes("-topmost", True)
        self.resizable(False, False)

        self.font_title = ui_font(size=18, weight="bold")
        self.font_labels = ui_font(size=14, weight="bold")
        self.font_keys = ui_font(size=13, weight="bold")

        self.grid_columnconfigure(0, weight=4) 
        self.grid_columnconfigure(1, weight=6) 
        self.grid_rowconfigure(0, weight=1)

        # 1. ΑΡΙΣΤΕΡΗ ΠΛΕΥΡΑ
        left_frame = ctk.CTkFrame(self, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        
        ctk.CTkLabel(left_frame, text="1. ΕΠΙΛΕΞΤΕ ΚΙΝΗΣΗ ΠΡΟΣΩΠΟΥ", font=self.font_title, text_color=self.MODERN_CYAN).pack(pady=(10, 15))
        
        motion_grid = ctk.CTkFrame(left_frame, fg_color="transparent")
        motion_grid.pack(fill="both", expand=True)
        motion_grid.grid_columnconfigure((0, 1), weight=1)
        
        facial_motions = [
            (short_display_name(name), name) for name in GESTURES
        ]

        for index, (label_text, motion_id) in enumerate(facial_motions):
            row = index // 2
            col = index % 2
            
            btn = ctk.CTkButton(
                motion_grid,
                text=label_text,
                font=self.font_labels,
                height=50,
                corner_radius=8,
                fg_color=self.BG_WIDGETS,
                border_color=self.BORDER_DEFAULT,
                border_width=1,
                text_color=self.TEXT_WHITE,
                hover_color="#2a2d37",
                command=lambda m=motion_id: self.select_motion(m)
            )
            btn.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            self.motion_buttons[motion_id] = btn

        # 2. ΔΕΞΙΑ ΠΛΕΥΡΑ
        right_frame = ctk.CTkFrame(self, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        ctk.CTkLabel(right_frame, text="2. ΕΠΙΛΕΞΤΕ ΠΛΗΚΤΡΟ ΑΝΤΙΣΤΟΙΧΗΣΗΣ", font=self.font_title, text_color=self.MODERN_GREEN).pack(pady=(10, 15))
        
        keyboard_grid = ctk.CTkFrame(right_frame, fg_color="transparent")
        keyboard_grid.pack(fill="both", expand=True)

        for row_keys in KEYBOARD_LAYOUT:
            row_frame = ctk.CTkFrame(keyboard_grid, fg_color="transparent")
            row_frame.pack(fill="x", pady=4)
            
            for key in row_keys:
                btn_width = 80 if key in ["space", "enter", "left_click", "right_click"] else 46
                display_text = key_label(key)

                btn = ctk.CTkButton(
                    row_frame,
                    text=display_text,
                    font=self.font_keys,
                    width=btn_width,
                    height=48,
                    corner_radius=6,
                    fg_color=self.BG_WIDGETS,
                    border_color=self.BORDER_DEFAULT,
                    border_width=1,
                    text_color=self.TEXT_WHITE,
                    hover_color="#2a2d37",
                    command=lambda k=key: self.select_key(k)
                )
                btn.pack(side="left", padx=3, expand=True, fill="both")
                self.key_buttons[key] = btn

        # 3. ΚΑΤΩ ΜΕΡΟΣ
        self.btn_save = ctk.CTkButton(
            right_frame, 
            text="Αποθήκευση Σύνδεσης", 
            font=self.font_title,
            height=55,
            corner_radius=10,
            fg_color="transparent",
            border_color=self.BORDER_DEFAULT,
            border_width=2,
            text_color=self.BORDER_DEFAULT,
            state="disabled",
            command=self.save_to_db
        )
        self.btn_save.pack(fill="x", pady=(20, 10))

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        # Μετά το χτίσιμο του UI, ώστε το ``wait_visibility()`` να μη δεσμεύσει
        # ένα κενό παράθυρο πριν προλάβει να εμφανιστεί το περιεχόμενο.
        grab_modal(self)

    def select_motion(self, motion_id):
        self.selected_motion = motion_id
        for btn in self.motion_buttons.values():
            btn.configure(border_color=self.BORDER_DEFAULT, fg_color=self.BG_WIDGETS, text_color=self.TEXT_WHITE)
        self.motion_buttons[motion_id].configure(border_color=self.MODERN_CYAN, fg_color="#002233", text_color=self.MODERN_CYAN)
        self.check_if_ready_to_save()

    def select_key(self, key_name):
        self.selected_key = key_name
        for btn in self.key_buttons.values():
            btn.configure(border_color=self.BORDER_DEFAULT, fg_color=self.BG_WIDGETS, text_color=self.TEXT_WHITE)
        self.key_buttons[key_name].configure(border_color=self.MODERN_GREEN, fg_color="#003322", text_color=self.MODERN_GREEN)
        self.check_if_ready_to_save()

    def check_if_ready_to_save(self):
        if self.selected_motion and self.selected_key:
            self.btn_save.configure(
                state="normal", 
                border_color=self.MODERN_GREEN, 
                text_color=self.MODERN_GREEN,
                hover_color="#004d33"
            )

    def save_to_db(self):
        if not self.selected_motion or not self.selected_key:
            return

        print(f"[HorusAccess] Προετοιμασία αποθήκευσης: {self.selected_motion} -> {self.selected_key}")

        try:
            # Χρησιμοποιούμε το τρέχον προφίλ του κύριου παραθύρου, ώστε αν ο
            # χρήστης αλλάξει προφίλ με το παράθυρο ανοιχτό, η κίνηση να πάει
            # στο σωστό προφίλ.
            profile_source = getattr(self.parent, 'current_profile_id', self.profile_id)
            if isinstance(profile_source, str):
                digits = [s for s in profile_source.split() if s.isdigit()]
                clean_id = int(digits[0]) if digits else 1
            else:
                clean_id = int(profile_source)

            # Keep the last click binding from being removed. A profile that
            # never had one (for example a 2D platformer profile) is still
            # allowed to store keyboard-only mappings.
            current = {row[1]: row[2] for row in self.db.get_mappings(clean_id)}
            pending = dict(current)
            pending[self.selected_motion] = self.selected_key
            had_click = any(
                canonical_key(key) == "left_click" for key in current.values()
            )
            has_click = any(
                canonical_key(key) == "left_click" for key in pending.values()
            )
            if had_click and not has_click:
                messagebox.showwarning(
                    "Απαιτείται Κλικ",
                    "Το αριστερό κλικ (L. CLICK) πρέπει να έχει πάντα μια κίνηση.\n\n"
                    "Διάλεξε πρώτα μια κίνηση για το L. CLICK και μετά άλλαξε αυτήν την αντιστοίχιση.",
                    parent=self,
                )
                return

            self.db.save_mapping(
                profile_id=clean_id,
                action=self.selected_motion,
                mapped_key=self.selected_key,
                default_threshold=default_threshold(self.selected_motion),
            )
            print(f"✅ Επιτυχής καταχώρηση στη βάση (Προφίλ: {clean_id})!")

        except Exception as e:
            print(f"❌ Σφάλμα κατά την εγγραφή στη βάση δεδομένων: {e}")

        # Κρατάμε το παράθυρο ανοιχτό μετά την καταχώρηση, ώστε να μπορούν να
        # προστεθούν και άλλες κινήσεις χωρίς να ξανανοίξει. Ελευθερώνουμε όμως
        # το modal grab, αλλιώς το κύριο παράθυρο (και η αλλαγή προφίλ) μένει
        # μπλοκαρισμένο όσο το παράθυρο είναι ανοιχτό.
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            if hasattr(self.parent, 'refresh_active_mappings'):
                self.parent.refresh_active_mappings()
            if hasattr(self.parent, 'load_profile_data'):
                self.parent.load_profile_data(getattr(self.parent, 'current_profile_id', self.profile_id))
        except Exception:
            pass
        self._reset_selection()

    def _reset_selection(self):
        """Καθαρίζει την τρέχουσα επιλογή και απενεργοποιεί το κουμπί αποθήκευσης."""
        self.selected_motion = None
        self.selected_key = None
        for btn in self.motion_buttons.values():
            btn.configure(border_color=self.BORDER_DEFAULT, fg_color=self.BG_WIDGETS, text_color=self.TEXT_WHITE)
        for btn in self.key_buttons.values():
            btn.configure(border_color=self.BORDER_DEFAULT, fg_color=self.BG_WIDGETS, text_color=self.TEXT_WHITE)
        self.btn_save.configure(
            state="disabled",
            border_color=self.BORDER_DEFAULT,
            text_color=self.BORDER_DEFAULT,
        )

    def on_close(self):
        self.grab_release()
        self.destroy()

class SmartControllerApp(SnapCursorMixin, ctk.CTk):
    def _release_all_keys(self):
        """Απελευθερώνει όλα τα πλήκτρα που κρατάει αυτή η εφαρμογή."""
        for key in list(getattr(self, "pressed_keys", ())):
            try:
                key_up(key)
            except Exception as exc:
                print(f"⚠️ Αποτυχία απελευθέρωσης '{key}': {exc}")
        self.pressed_keys.clear()

    def refresh_active_mappings(self):
        # Τα παλιά mappings μπορεί να κρατούν πατημένο ένα πλήκτρο που δεν
        # υπάρχει πλέον, οπότε απελευθερώνουμε πριν τα αντικαταστήσουμε.
        self._release_all_keys()
        mappings = self.db.get_mappings(self.current_profile_id)
        self.active_mappings.clear()
        
        for m_id, action, key, threshold in mappings:
            canonical = canonical_motion(action)
            if canonical is None:
                print(f"⚠️ Παράλειψη άγνωστης κίνησης στη βάση: {action}")
                continue
            self.active_mappings[canonical] = {"key": key, "threshold": threshold}
            
        print(f"Ενεργά Mappings ανανεώθηκαν: {self.active_mappings}")

    def __init__(self, show_face_mesh=True):
            super().__init__()  # Το super() πρέπει να καλείται πρώτο
    
            self.active_mappings = {}
            self.pressed_keys = set()
            self._sens_save_job = None
            # Overlay switch, wired up in HorusAccess/main.py (SHOW_FACE_MESH).
            self.show_face_mesh = show_face_mesh
            # (timestamp, centre points) of the controls, refreshed lazily.
            self._snap_cache = (0.0, [])
    
            self.title("Smart Controller - Σχεδίαση & Υλοποίηση")
            self.geometry("1100x700")
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")
    
            self.db = DBManager()
            self.current_profile_id = self.db.get_last_profile()

            # Μία φορά: αντικαθιστούμε το παλιό ενιαίο 0.05 με τα όρια ανά κίνηση.
            try:
                migrated = self.db.migrate_legacy_thresholds(default_thresholds())
                if migrated:
                    print(f"🔧 Μεταφέρθηκαν {migrated} παλιά όρια κινήσεων.")
            except Exception as e:
                print(f"⚠️ Αποτυχία μεταφοράς παλιών ορίων: {e}")

            # Μία φορά: παλιά spellings πλήκτρων -> canonical μορφή.
            try:
                migrated_keys = self.db.migrate_legacy_key_aliases()
                if migrated_keys:
                    print(f"🔧 Μεταφέρθηκαν {migrated_keys} παλιά ονόματα πλήκτρων.")
            except Exception as e:
                print(f"⚠️ Αποτυχία μεταφοράς παλιών ονομάτων πλήκτρων: {e}")

            # Μία φορά: παλιά ονόματα κινήσεων (kiss) -> canonical μορφή.
            try:
                migrated_actions = self.db.migrate_legacy_action_aliases()
                if migrated_actions:
                    print(f"🔧 Ενοποιήθηκαν {migrated_actions} παλιές κινήσεις.")
            except Exception as e:
                print(f"⚠️ Αποτυχία μεταφοράς παλιών κινήσεων: {e}")

            # Η ουδέτερη στάση κεφαλιού καταγράφεται μόλις ξεκινήσει η κάμερα.
            self.head_tracker = HeadPoseTracker()
            self._head_was_calibrated = False
            
            # --- MediaPipe Setup ---
            self.mp_face_mesh = mp.solutions.face_mesh
            self.face_mesh = self.mp_face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True, 
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )

            # Συνδέσεις για το πλέγμα που σχεδιάζεται πάνω στο πρόσωπο. Τα
            # εικονοστοιχεία υπολογίζονται μία φορά και κάθε σύνολο σχεδιάζεται
            # με ένα cv2.polylines (η ανά-γραμμή έκδοση κοστίζει 4x περισσότερο).
            self._mesh_edges = np.array(
                sorted(self.mp_face_mesh.FACEMESH_TESSELATION), dtype=np.int32
            )
            self._contour_edges = np.array(
                sorted(self.mp_face_mesh.FACEMESH_CONTOURS), dtype=np.int32
            )
            self._iris_edges = np.array(
                sorted(self.mp_face_mesh.FACEMESH_IRISES), dtype=np.int32
            )
    
            # --- Παράμετροι Ποντικιού ---
            # Χρήση του screen_size() για ασφάλεια στις διαστάσεις
            self.screen_w, self.screen_h = screen_size()
            self.mouse_control_active = True 

            # Head tracking works over every window, including our own UI: the
            # cursor still has to reach the app's buttons. Physical mouse
            # movement temporarily takes over instead (see the override below).
            # False when the user grabbed the mouse; refreshed on every physical
            # movement so head tracking steps aside while they interact.
            self._mouse_activity_seen = mouse_activity_count()
            self._mouse_override_until = 0.0

            self.virtual_x, self.virtual_y = float(self.screen_w // 2), float(self.screen_h // 2)
    
            self._build_ui()
            self.load_profile_data(self.current_profile_id)
            self.refresh_active_mappings()
            
            # --- OpenCV Setup ---
            # Το backend της κάμερας επιλέγεται αυτόματα ανά OS (DSHOW/V4L2/AVFoundation)
            print("🔍 Προσπάθεια ανοίγματος της κάμερας στο ID: 0...")
            self.cap = open_webcam(0, 640, 480)

            if self.cap is None or not self.cap.isOpened():
                print("❌ Αποτυχία ανοίγματος κάμερας!")
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None
            else:
                print("✅ Η κάμερα στο ID 0 άνοιξε επιτυχώς!")
    
            # --- Σωστή εκκίνηση του Video Loop ---
            # Χρησιμοποιούμε after() ώστε το UI να προλάβει να εμφανιστεί πρώτα!
            self.after(100, self.start_video_loop)
    
    def start_video_loop(self):
        self.update_video()
             # Καλεί το update_video ξανά μετά από 15ms (~60 FPS)
        self.after(15, self.start_video_loop)

    def _build_ui(self):
        """Κατασκευάζει το User Interface σε Μοντέρνο Stealth Στυλ."""
        ctk.set_appearance_mode("Dark")
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        font_main = ui_font(size=16, weight="bold")
        font_logo = ui_font(size=20, weight="bold")

        BG_MAIN = "#111215"          
        BG_SIDEBAR = "#16171b"       
        BG_WIDGETS = "#1f2128"       
        
        MODERN_CYAN = "#00f0ff"      
        MODERN_GREEN = "#00ffaa"     
        
        TEXT_WHITE = "#ffffff"
        TEXT_MUTED = "#6c7281"

        self.configure(fg_color=BG_MAIN)

        # ==========================================
        # 1. SIDEBAR (Αριστερή Πλευρά)
        # ==========================================
        self.sidebar = ctk.CTkFrame(self, width=320, corner_radius=0, fg_color=BG_SIDEBAR, border_width=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.sidebar.grid_propagate(False)
        
        ctk.CTkLabel(self.sidebar, text="CONTROLLER INTERFACE", font=font_main, text_color=TEXT_MUTED).pack(pady=(35, 20))

        # --- Επιλογή Προφίλ ---
        ctk.CTkLabel(self.sidebar, text="Επιλογή Προφίλ", font=font_main, text_color=TEXT_WHITE).pack(pady=(10, 5), anchor="w", padx=25)
        
        self.profile_selector = ctk.CTkSegmentedButton(
            self.sidebar, 
            values=["1", "2", "3", "4", "5"], 
            font=font_main, 
            height=42,
            fg_color=BG_WIDGETS,
            selected_color=MODERN_GREEN,
            selected_hover_color=MODERN_CYAN,
            text_color=TEXT_WHITE,
            command=self.change_profile
        )
        self.profile_selector.set(str(getattr(self, 'current_profile_id', 1)))
        self.profile_selector.pack(pady=10, padx=20, fill="x")

        # --- Ευαισθησία ---
        ctk.CTkLabel(self.sidebar, text="Ευαισθησία", font=font_main, text_color=TEXT_WHITE).pack(pady=(25, 5), anchor="w", padx=25)
        
        self.sens_slider = ctk.CTkSlider(
            self.sidebar, 
            from_=0.1, 
            to=3.0, 
            number_of_steps=29, 
            command=self.update_sens_label, 
            height=20, 
            button_length=22,
            fg_color=BG_WIDGETS,
            progress_color=MODERN_CYAN,   
            button_color=MODERN_GREEN,    
            button_hover_color=MODERN_CYAN
        ) 
        self.sens_slider.set(1.0)
        self.sens_slider.pack(pady=10, padx=20, fill="x")
        
        self.sens_value_label = ctk.CTkLabel(self.sidebar, text="1.0", font=font_main, text_color=MODERN_GREEN)
        self.sens_value_label.pack(pady=(0, 12))

        # --- Κέντρο Κεφαλιού ---
        ctk.CTkLabel(self.sidebar, text="Κέντρο Κεφαλιού", font=font_main, text_color=TEXT_WHITE).pack(pady=(4, 5), anchor="w", padx=25)

        self.head_status_label = ctk.CTkLabel(
            self.sidebar,
            text="⏳ Μέτρηση ουδέτερης στάσης...",
            font=ui_font(size=12),
            text_color=TEXT_MUTED,
        )
        self.head_status_label.pack(pady=(0, 5), padx=25, anchor="w")

        self.btn_head_reset = ctk.CTkButton(
            self.sidebar,
            text="🎯 Επαναφορά Κέντρου",
            font=ui_font(size=13, weight="bold"),
            height=36,
            corner_radius=10,
            fg_color="transparent",
            border_color=MODERN_GREEN,
            border_width=2,
            text_color=MODERN_GREEN,
            hover_color="#004d33",
            command=self.reset_head_center,
        )
        self.btn_head_reset.pack(pady=(0, 12), padx=20, fill="x")

        # --- Κουμπί 1: Εισαγωγή Κίνησης ---
        self.btn_add_motion = ctk.CTkButton(
            self.sidebar, 
            text="Εισαγωγή Κίνησης", 
            font=font_main, 
            height=55, 
            corner_radius=12,
            fg_color="transparent",
            border_color=MODERN_CYAN,
            border_width=2,
            text_color=MODERN_CYAN,
            hover_color="#004455",
            command=self.add_motion_event
        )
        self.btn_add_motion.pack(pady=8, padx=20, fill="x")

        # --- Κουμπί 2: Εμφάνιση Καταχωρημένων ---
        self.btn_review = ctk.CTkButton(
            self.sidebar, 
            text="Εμφάνιση Καταχωρημένων", 
            font=font_main, 
            height=50, 
            corner_radius=12,
            fg_color="transparent",
            border_color=MODERN_GREEN,
            border_width=2,
            text_color=MODERN_GREEN,
            hover_color="#004d33",
            command=self.open_review_window
        )
        self.btn_review.pack(pady=8, padx=20, fill="x")

        # --- Κουμπί 3: ΑΥΤΟΝΟΜΗ ΕΠΙΛΟΓΗ (ΑΚΡΙΒΩΣ ΚΑΤΩ ΑΠΟ ΤΗΝ ΕΜΦΑΝΙΣΗ ΚΑΤΑΧΩΡΗΜΕΝΩΝ) ---
        self.btn_auto_select = ctk.CTkButton(
            self.sidebar,
            text="ΕΠΙΛΟΓΗ HORUS AI",
            font=font_main,
            height=55,
            corner_radius=12,
            fg_color=MODERN_CYAN,
            text_color="#111215",
            hover_color=MODERN_GREEN,
            command=self.open_autonomous_selector
        )
        self.btn_auto_select.pack(pady=(15, 10), padx=20, fill="x")

        # ==========================================
        # 2. MAIN AREA (Δεξιά Πλευρά)
        # ==========================================
        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        self.main_area.grid_rowconfigure(1, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)

        # --- TOP BAR ---
        self.top_bar = ctk.CTkFrame(self.main_area, fg_color="transparent", height=40)
        self.top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        
        self.logo_label = ctk.CTkLabel(
            self.top_bar, 
            text="Horus Access", 
            font=font_logo, 
            text_color=MODERN_CYAN
        )
        self.logo_label.pack(side="right", padx=5)

        # --- VIDEO AREA ---
        self.video_frame = ctk.CTkFrame(
            self.main_area, 
            corner_radius=16, 
            fg_color="#181a20", 
            border_width=2,
            border_color=MODERN_CYAN
        )
        self.video_frame.grid(row=1, column=0, sticky="nsew")
        
        self.video_label = ctk.CTkLabel(self.video_frame, text="[ Video Stream Active ]", font=font_main, text_color=TEXT_MUTED)
        self.video_label.pack(expand=True, fill="both", padx=10, pady=10)
        # Μία μόνο PhotoImage για όλα τα frames· ενημερώνεται in-place με paste().
        self._video_photo = None

    def open_autonomous_selector(self):
        """Ανοίγει το παράθυρο πλέγματος των 6 παιχνιδιών."""
        AutonomousGameSelectorWindow(self)

    def change_profile(self, value):
        self.current_profile_id = int(value)
        self.db.set_last_profile(self.current_profile_id)
        print(f"--- Αλλαγή σε Προφίλ {self.current_profile_id} ---")
        self.refresh_active_mappings()
        self.load_profile_data(self.current_profile_id)

    def reset_head_center(self):
        """Ξεκινά νέα μέτρηση της ουδέτερης στάσης κεφαλιού."""
        if not hasattr(self, "head_tracker"):
            return
        self.head_tracker.reset()
        self._head_was_calibrated = False
        if hasattr(self, "head_status_label"):
            self.head_status_label.configure(
                text="⏳ Μέτρηση ουδέτερης στάσης...",
                text_color="#6c7281",
            )
        print("🎯 Νέο κέντρο κεφαλιού: κρατήστε το κεφάλι σε ουδέτερη στάση.")

    def load_profile_data(self, profile_id):
        profiles = self.db.get_all_profiles()
        for p in profiles:
            if p[0] == profile_id:
                self.sens_slider.set(p[2])
                self.sens_value_label.configure(text=f"{p[2]:.1f}")
                break

    def update_sens_label(self, value):
        if hasattr(self, "sens_value_label"):
            self.sens_value_label.configure(text=f"{value:.1f}")
        self._schedule_sensitivity_save()

    def _schedule_sensitivity_save(self):
        """Αποθηκεύει την ευαισθησία 400ms μετά την τελευταία αλλαγή."""
        if not hasattr(self, "db") or not hasattr(self, "current_profile_id"):
            return
        if self._sens_save_job is not None:
            try:
                self.after_cancel(self._sens_save_job)
            except Exception:
                pass
        self._sens_save_job = self.after(400, self._persist_sensitivity)

    def _persist_sensitivity(self):
        self._sens_save_job = None
        try:
            value = float(self.sens_slider.get())
            self.db.update_profile_sensitivity(self.current_profile_id, value)
        except Exception as e:
            print(f"⚠️ Αποτυχία αποθήκευσης ευαισθησίας: {e}")

    def _draw_face_overlay(self, frame, face_landmarks):
        """Σχεδιάζει το πλέγμα του προσώπου πάνω στο frame.

        Τα σημεία προβάλλονται μία φορά σε pixel και κάθε σύνολο συνδέσεων
        σχεδιάζεται με μία κλήση ``cv2.polylines``. Χωρίς antialiasing, γιατί
        στο 640x480 η ομαλή γραμμή κοστίζει ~20ms/frame, ενώ έτσι ~3ms.
        """
        height, width = frame.shape[:2]
        points = np.array(
            [(lm.x * width, lm.y * height) for lm in face_landmarks.landmark],
            dtype=np.int32,
        )
        if points.size == 0:
            return

        cv2.polylines(
            frame, points[self._mesh_edges], False, (0, 130, 140), 1, cv2.LINE_8
        )
        cv2.polylines(
            frame, points[self._contour_edges], False, (0, 240, 255), 1, cv2.LINE_8
        )
        # Τα iris landmarks (469-477) υπάρχουν μόνο με refine_landmarks=True.
        if points.shape[0] > int(self._iris_edges.max()):
            cv2.polylines(
                frame, points[self._iris_edges], False, (0, 240, 255), 1, cv2.LINE_8
            )

    def update_video(self):
        if self.cap is None:
            return

        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                return

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb_frame)

            if results and results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    # Οπτική επιβεβαίωση ανίχνευσης, ανεξάρτητα από το αν η
                    # κίνηση του ποντικιού είναι σε παύση.
                    if getattr(self, 'show_face_mesh', True):
                        self._draw_face_overlay(rgb_frame, face_landmarks)

                    # Needed by both the mouse-move branch and the mouth-click
                    # check below, so compute it before the branch.
                    sens_val = 1.0
                    if hasattr(self, 'sens_slider'):
                        try:
                            sens_val = float(self.sens_slider.get())
                        except Exception:
                            sens_val = 1.0

                    if getattr(self, 'mouse_control_active', False):
                        current_time = time.time()

                        # Αν ο χρήστης κουνήσει το πραγματικό ποντίκι, σταματάμε
                        # προσωρινά το warp: αλλιώς κάθε καρέ θα τραβάει τον
                        # δείκτη πίσω και δεν θα μπορεί να πατήσει τίποτα.
                        activity = mouse_activity_count()
                        if activity != self._mouse_activity_seen:
                            self._mouse_activity_seen = activity
                            self._mouse_override_until = (
                                current_time + MOUSE_OVERRIDE_SECONDS
                            )
                        manual_override = current_time < self._mouse_override_until

                        # Landmarks
                        nose = face_landmarks.landmark[1]
                        left_face = face_landmarks.landmark[234]
                        right_face = face_landmarks.landmark[454]
                        top_face = face_landmarks.landmark[10]
                        bottom_face = face_landmarks.landmark[152]

                        # 1. Υπολογισμός Γωνίας Κλίσης Κεφαλιού (Roll - Δεξιά/Αριστερά)
                        roll_tilt = right_face.y - left_face.y

                        # 2. Υπολογισμός Πάνω/Κάτω (Pitch)
                        face_center_y = (top_face.y + bottom_face.y) / 2.0
                        pitch_tilt = nose.y - face_center_y

                        # 3. Νεκρές Ζώνες (Deadzones)
                        deadzone_roll = 0.025   # Ανοχή στο γέρσιμο
                        deadzone_pitch = 0.005  # Πολύ ευαίσθητο στο πάνω/κάτω (ξεκινάει αμέσως)

                        move_x = 0.0
                        move_y = 0.0

                        # 4. Υπολογισμός κίνησης X βάσει γέρσιματος (Roll)
                        if abs(roll_tilt) > deadzone_roll:
                            # Το frame είναι οριζόντια flipped, οπότε το
                            # roll_tilt μεγαλώνει όταν ο χρήστης γέρνει
                            # αριστερά· το πρόσημο αντιστρέφεται ώστε ο
                            # δείκτης να ακολουθεί τη φυσική κατεύθυνση.
                            sign_x = 1 if roll_tilt > 0 else -1
                            excess_x = abs(roll_tilt) - deadzone_roll
                            move_x = sign_x * (excess_x * 500 * sens_val)

                        # 5. Υπολογισμός κίνησης Y βάσει κλίσης πάνω/κάτω (Pitch)
                        if abs(pitch_tilt) > deadzone_pitch:
                            sign_y = 1 if pitch_tilt > 0 else -1
                            excess_y = abs(pitch_tilt) - deadzone_pitch
                            # Αυξημένος πολλαπλασιαστής (1200) για υπερ-ταχεία απόκριση με ελάχιστη κίνηση
                            move_y = sign_y * (excess_y * 1200 * sens_val)

                        # 6. Ενημέρωση εικονικών συντεταγμένων
                        if not hasattr(self, 'virtual_x'):
                            init_x, init_y = mouse_position()
                            self.virtual_x = float(init_x)
                            self.virtual_y = float(init_y)

                        self.virtual_x += move_x
                        self.virtual_y += move_y

                        # 7. Όρια οθόνης
                        screen_w = getattr(self, 'screen_w', 1920)
                        screen_h = getattr(self, 'screen_h', 1080)

                        self.virtual_x = max(0, min(screen_w - 1, self.virtual_x))
                        self.virtual_y = max(0, min(screen_h - 1, self.virtual_y))

                        # 8. Εκτέλεση κίνησης
                        if manual_override:
                            # Ο χρήστης έχει το ποντίκι. Δεν το τραβάμε πίσω·
                            # απλώς ακολουθούμε τη θέση του, ώστε όταν αναλάβει
                            # ξανά η ιχνηλάτηση να μην πηδήξει ο δείκτης.
                            try:
                                cur_x, cur_y = mouse_position()
                                self.virtual_x = float(cur_x)
                                self.virtual_y = float(cur_y)
                            except Exception:
                                pass
                            cv2.putText(rgb_frame, "PAUSED (MOUSE OVERRIDE)", (10, 30), 0, 0.8, (0, 0, 255), 2)
                        else:
                            target_x = int(self.virtual_x)
                            target_y = int(self.virtual_y)
                            target_x, target_y = self._snap_cursor(target_x, target_y)
                            mouse_move(target_x, target_y)
                    else:
                        # Re-sync the virtual cursor to the real pointer so the
                        # mouse does not jump once tracking resumes.
                        try:
                            cur_x, cur_y = mouse_position()
                            self.virtual_x = float(cur_x)
                            self.virtual_y = float(cur_y)
                        except Exception:
                            pass
                        # Absorb any movement seen while paused, so returning to
                        # tracking does not immediately trigger the override.
                        self._mouse_activity_seen = mouse_activity_count()
                        cv2.putText(rgb_frame, "PAUSED (TRACKING OFF)", (10, 30), 0, 0.8, (0, 0, 255), 2)

                    # Gestures
                    try:
                        landmarks = face_landmarks.landmark
                        current_metrics = compute_facial_metrics(landmarks)
                        current_metrics.update(self.head_tracker.update(landmarks))

                        if self.head_tracker.is_calibrated != self._head_was_calibrated:
                            self._head_was_calibrated = self.head_tracker.is_calibrated
                            if self._head_was_calibrated:
                                self.head_status_label.configure(
                                    text="✅ Κέντρο κεφαλιού καταγράφηκε",
                                    text_color="#00ffaa",
                                )
                                print("✅ Καταγράφηκε το κέντρο κεφαλιού.")
                            else:
                                self.head_status_label.configure(
                                    text="⏳ Μέτρηση ουδέτερης στάσης...",
                                    text_color="#6c7281",
                                )

                        active_mappings = getattr(self, 'active_mappings', {})
                        pressed_keys = getattr(self, 'pressed_keys', set())

                        # Πρώτα υπολογίζουμε ποια πλήκτρα πρέπει να είναι πατημένα,
                        # ώστε ένα πλήκτρο που το διεκδικούν δύο κινήσεις να μην
                        # απελευθερώνεται όταν σταματήσει μόνο η μία.
                        desired_keys = set()
                        for action, data in active_mappings.items():
                            target_key = canonical_key(data.get("key"))
                            action = canonical_motion(action)
                            threshold = data.get("threshold")

                            if not target_key or action is None:
                                continue
                            if threshold is None:
                                threshold = default_threshold(action)

                            if is_gesture_active(
                                action, current_metrics.get(action), threshold
                            ):
                                desired_keys.add(target_key)

                        for target_key in sorted(desired_keys - pressed_keys):
                            key_down(target_key)
                            pressed_keys.add(target_key)
                            print(f"🟢 [ΕΝΕΡΓΟ] Πατήθηκε: {target_key.upper()}")

                        for target_key in sorted(pressed_keys - desired_keys):
                            key_up(target_key)
                            pressed_keys.discard(target_key)
                            print(f"🔴 [ΑΝΕΝΕΡΓΟ] Απελευθερώθηκε: {target_key.upper()}")

                    except Exception as e:
                        print(f"❌ ΣΦΑΛΜΑ ΣΤΑ GESTURES: {e}")
            else:
                # Το πρόσωπο χάθηκε (κοίταξε αλλού / κόλλησε η κάμερα). Χωρίς
                # αυτό, όποιο πλήκτρο ήταν πατημένο θα έμενε πατημένο για πάντα.
                self._release_all_keys()

            img = Image.fromarray(rgb_frame)
            if self._video_photo is None:
                self._video_photo = ImageTk.PhotoImage(img)
                # Το CTkLabel προειδοποιεί για μη-CTkImage· εδώ η σταθερή
                # PhotoImage είναι σκόπιμη, ώστε να ενημερώνεται in-place.
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message=".*Image can not be scaled on HighDPI displays.*",
                        category=UserWarning,
                    )
                    self.video_label.configure(image=self._video_photo, text="")
            else:
                photo_size = (self._video_photo.width(), self._video_photo.height())
                if img.size != photo_size:
                    img = img.resize(photo_size, Image.Resampling.BILINEAR)
                # Ενημερώνει την ίδια PhotoImage χωρίς νέα allocation ανά frame.
                self._video_photo.paste(img)

        except Exception as global_err:
            print(f"⚠️ Σφάλμα στο update_video: {global_err}")

    def add_motion_event(self):
        db_instance = getattr(self, 'db', None)
        current_profile = self.profile_selector.get()
        print("DEBUG: Add motion button pressed")
        MotionInputWindow(self, current_profile, db_instance)

    def open_review_window(self):
        review_popup = ProfileReviewWindow(self, self.current_profile_id, self.db)
        grab_modal(review_popup)

    def on_closing(self):
        if self._sens_save_job is not None:
            try:
                self.after_cancel(self._sens_save_job)
            except Exception:
                pass
            self._persist_sensitivity()
        self._release_all_keys()
        try:
            self.db.set_last_profile(self.current_profile_id)
        except Exception:
            pass
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.destroy()

if __name__ == "__main__":
    app = SmartControllerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
