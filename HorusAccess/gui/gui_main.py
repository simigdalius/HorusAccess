import customtkinter as ctk
import cv2
import mediapipe as mp
from PIL import Image
import pydirectinput
import time
import math
import os
import sys
import pyautogui
from database.db_manager import DBManager


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Απενεργοποίηση του FailSafe για να μην κρασάρει αν το ποντίκι πάει στις γωνίες
pydirectinput.FAILSAFE = False

class ProfileReviewWindow(ctk.CTkToplevel):
    def __init__(self, parent, current_profile_id, db):
        super().__init__(parent)
        
        self.parent = parent
        self.profile_id = current_profile_id
        self.db = db

        self.title(f"Εμφάνιση & Επεξεργασία Καταχωρημένων (Προφίλ {self.profile_id})")
        self.geometry("750x550")
        self.attributes("-topmost", True)

        # Αποθήκευση αναφορών στα widgets (για να μπορούμε να τα διαβάσουμε/κλειδώσουμε)
        self.row_widgets = {} 
        self.is_locked = False

        self._build_ui()
        self.load_data()

    def _build_ui(self):
        # Τίτλος
        ctk.CTkLabel(self, text="Διαχείριση Κινήσεων", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=20)

        # Scrollable Frame για τη λίστα
        self.scroll_frame = ctk.CTkScrollableFrame(self, width=650, height=350)
        self.scroll_frame.pack(pady=10, padx=20, fill="both", expand=True)

        # Κουμπί Αποθήκευσης & Κλειδώματος
        self.btn_lock = ctk.CTkButton(self, text="Αποθήκευση & Κλείδωμα", 
                                      font=ctk.CTkFont(size=18, weight="bold"), 
                                      height=50, fg_color="#27ae60", hover_color="#2ecc71",
                                      command=self.save_and_lock)
        self.btn_lock.pack(pady=20)

    def load_data(self):
        # Καθαρισμός του frame σε περίπτωση ανανέωσης
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.row_widgets.clear()

        mappings = self.db.get_mappings(self.profile_id)
        
        if not mappings:
            ctk.CTkLabel(self.scroll_frame, text="Δεν βρέθηκαν καταχωρημένες κινήσεις.", font=ctk.CTkFont(size=16)).pack(pady=40)
            return

        # Δημιουργία γραμμής (Row) για κάθε καταχωρημένη κίνηση
        for m_id, action, key, threshold in mappings:
            row_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=8)
            row_frame.pack(fill="x", pady=5, padx=5, ipady=5)

            # Όνομα Κίνησης
            ctk.CTkLabel(row_frame, text=f"🎯 {action}", font=ctk.CTkFont(size=16, weight="bold"), width=150, anchor="w").pack(side="left", padx=10)

            # Dropdown Πλήκτρου
            ctk.CTkLabel(row_frame, text="Πλήκτρο:").pack(side="left", padx=(10, 2))
            key_var = ctk.StringVar(value=key)
            key_dropdown = ctk.CTkOptionMenu(row_frame, values=["space", "enter", "w", "a", "s", "d", "up", "down", "left_click", "right_click"], variable=key_var, width=100, state="disabled")
            key_dropdown.pack(side="left", padx=5)

            # Entry Ευαισθησίας
            ctk.CTkLabel(row_frame, text="Όριο (Thresh):").pack(side="left", padx=(15, 2))
            thresh_entry = ctk.CTkEntry(row_frame, width=60, state="disabled")
            thresh_entry.insert(0, str(threshold))
            thresh_entry.pack(side="left", padx=5)

            # Κουμπιά Action
            btn_edit = ctk.CTkButton(row_frame, text="Επεξεργασία", width=80, fg_color="#f39c12", hover_color="#e67e22",
                                     command=lambda mid=m_id: self.enable_edit(mid))
            btn_edit.pack(side="right", padx=10)

            btn_delete = ctk.CTkButton(row_frame, text="Διαγραφή", width=80, fg_color="#c0392b", hover_color="#e74c3c",
                                       command=lambda mid=m_id: self.delete_entry(mid))
            btn_delete.pack(side="right", padx=5)

            # Αποθήκευση των στοιχείων για να τα ελέγχουμε αργότερα
            self.row_widgets[m_id] = {
                "key_dropdown": key_dropdown,
                "thresh_entry": thresh_entry,
                "btn_edit": btn_edit,
                "btn_delete": btn_delete
            }

    def enable_edit(self, mapping_id):
        """Ξεκλειδώνει τα πεδία μιας συγκεκριμένης γραμμής."""
        if self.is_locked:
            return # Αν είναι συνολικά κλειδωμένο, αγνοούμε το πάτημα
            
        widgets = self.row_widgets[mapping_id]
        widgets["key_dropdown"].configure(state="normal")
        widgets["thresh_entry"].configure(state="normal")
        widgets["btn_edit"].configure(text="Ενεργό", fg_color="gray", state="disabled")

    def delete_entry(self, mapping_id):
        """Διαγράφει την κίνηση και ανανεώνει τη λίστα."""
        if self.is_locked:
            return

        self.db.delete_mapping(mapping_id)
        print(f"Διαγράφηκε η κίνηση με ID {mapping_id}")
        self.load_data() # Ανανέωση UI
        self.parent.refresh_active_mappings() # Ενημέρωση μνήμης στο background

    def save_and_lock(self):
        """Αποθηκεύει τις αλλαγές, κλειδώνει το UI και ετοιμάζει το σύστημα για gaming."""
        if self.is_locked:
            # Λειτουργία 'Ξεκλείδωμα'
            self.is_locked = False
            self.btn_lock.configure(text="Αποθήκευση & Κλείδωμα", fg_color="#27ae60", hover_color="#2ecc71")
            
            # Επαναφέρουμε τα Edit/Delete κουμπιά
            for w in self.row_widgets.values():
                w["btn_edit"].configure(state="normal", text="Επεξεργασία", fg_color="#f39c12")
                w["btn_delete"].configure(state="normal")
            return

        # Λειτουργία 'Αποθήκευση & Κλείδωμα'
        for m_id, widgets in self.row_widgets.items():
            new_key = widgets["key_dropdown"].get()
            try:
                new_thresh = float(widgets["thresh_entry"].get())
            except ValueError:
                new_thresh = 0.05 # Fallback αν ο χρήστης βάλει γράμματα αντί για αριθμούς

            # Ενημέρωση Βάσης
            self.db.update_mapping(m_id, new_key, new_thresh)
            
            # Κλείδωμα των widgets
            widgets["key_dropdown"].configure(state="disabled")
            widgets["thresh_entry"].configure(state="disabled")
            widgets["btn_edit"].configure(state="disabled")
            widgets["btn_delete"].configure(state="disabled")

        self.is_locked = True
        self.btn_lock.configure(text="🔒 ΚΛΕΙΔΩΜΕΝΟ (Πατήστε για ξεκλείδωμα)", fg_color="#c0392b", hover_color="#e74c3c")
        
        # Ενημέρωση της κεντρικής εφαρμογής με τα νέα δεδομένα
        self.parent.refresh_active_mappings()
        print("Το προφίλ αποθηκεύτηκε και κλειδώθηκε.")

class MotionRegistrationWindow(ctk.CTkToplevel):
    def __init__(self, parent, current_profile_id, db):
        super().__init__(parent)
        self.parent = parent
        self.profile_id = current_profile_id
        self.db = db

        # Ρυθμίσεις παραθύρου
        self.title("Εισαγωγή Κίνησης")
        self.geometry("500x550")
        self.attributes("-topmost", True)
        self.resizable(False, False)

        # Μεταβλητές αναπαραγωγής
        self.playback_frames = []
        self.playback_index = 0
        self.is_playing = False

        # --- UI Στοιχεία ---
        # 1. Περιοχή αναπαραγωγής βίντεο
        self.video_label = ctk.CTkLabel(self, text="", width=320, height=240, fg_color="gray20")
        self.video_label.pack(pady=20)

        # 2. Κείμενο Πληροφοριών / Αντίστροφης μέτρησης
        self.info_label = ctk.CTkLabel(self, text="Ετοιμαστείτε...", font=ctk.CTkFont(size=22, weight="bold"))
        self.info_label.pack(pady=10)

        # 3. Frame για τα κουμπιά Έγκρισης (Αρχικά κρυμμένο)
        self.approval_frame = ctk.CTkFrame(self, fg_color="transparent")
        
        self.btn_yes = ctk.CTkButton(self.approval_frame, text="Ναι (Έγκριση)", fg_color="green", hover_color="#006400", command=self.approve_motion)
        self.btn_yes.grid(row=0, column=0, padx=10)
        
        self.btn_no = ctk.CTkButton(self.approval_frame, text="Ξανά Καταγραφή", fg_color="#b22222", hover_color="#8b0000", command=self.retry_recording)
        self.btn_no.grid(row=0, column=1, padx=10)

        # 4. Frame για την Αντιστοίχιση Πλήκτρου (Αρχικά κρυμμένο)
        self.mapping_frame = ctk.CTkFrame(self, fg_color="transparent")

        ctk.CTkLabel(self.mapping_frame, text="Όνομα Κίνησης:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        
        self.action_dropdown = ctk.CTkOptionMenu(
            self, 
            values=["mouth_open", "smile", "left_eye_blink", "right_eye_blink"],
            font=ctk.CTkFont(size=16)
        )
        self.action_dropdown.pack(pady=(5, 20))
        self.action_dropdown.grid(row=0, column=1, padx=10, pady=10)

        ctk.CTkLabel(self.mapping_frame, text="Πλήκτρο:").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        self.key_dropdown = ctk.CTkOptionMenu(self.mapping_frame, values=["space", "enter", "w", "a", "s", "d", "up", "down", "left_click", "right_click"])
        self.key_dropdown.grid(row=1, column=1, padx=10, pady=10)

        self.btn_save = ctk.CTkButton(self.mapping_frame, text="Αποθήκευση & Κλείσιμο", command=self.save_to_db)
        self.btn_save.grid(row=2, column=0, columnspan=2, pady=20)

        # Αποτροπή σφαλμάτων αν κλείσει το παράθυρο νωρίς
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Έναρξη
        self.start_countdown()

    def auto_categorize_movement(self, recorded_landmarks):
        """Αναλύει τα καρέ και βρίσκει ποια από τις 10 κινήσεις έγινε."""
        if not recorded_landmarks:
            return None, 0.0

        import math

        # 1. Ετοιμάζουμε τις κενές λίστες
        metrics = {
            "mouth_open": [], "smile": [], "eyebrows_up": [], 
            "left_eye_blink": [], "right_eye_blink": [], "kiss": [], 
            "jaw_left": [], "jaw_right": [], "nose_scrunch": [], "cheek_puff": []
        }

        # 2. Γεμίζουμε τις λίστες με τις αποστάσεις από κάθε καρέ
        for face_landmarks in recorded_landmarks:
            landmarks = face_landmarks.landmark
            
            metrics["mouth_open"].append(math.hypot(landmarks[13].x - landmarks[14].x, landmarks[13].y - landmarks[14].y))
            metrics["smile"].append(math.hypot(landmarks[61].x - landmarks[291].x, landmarks[61].y - landmarks[291].y))
            metrics["eyebrows_up"].append((math.hypot(landmarks[105].x - landmarks[159].x, landmarks[105].y - landmarks[159].y) + math.hypot(landmarks[336].x - landmarks[386].x, landmarks[336].y - landmarks[386].y)) / 2)
            metrics["left_eye_blink"].append(math.hypot(landmarks[159].x - landmarks[145].x, landmarks[159].y - landmarks[145].y))
            metrics["right_eye_blink"].append(math.hypot(landmarks[386].x - landmarks[374].x, landmarks[386].y - landmarks[374].y))
            metrics["kiss"].append(math.hypot(landmarks[61].x - landmarks[291].x, landmarks[61].y - landmarks[291].y))
            metrics["jaw_left"].append(math.hypot(landmarks[152].x - landmarks[132].x, landmarks[152].y - landmarks[132].y))
            metrics["jaw_right"].append(math.hypot(landmarks[152].x - landmarks[361].x, landmarks[152].y - landmarks[361].y))
            metrics["nose_scrunch"].append(math.hypot(landmarks[1].x - landmarks[13].x, landmarks[1].y - landmarks[13].y))
            metrics["cheek_puff"].append(math.hypot(landmarks[50].x - landmarks[280].x, landmarks[50].y - landmarks[280].y))

        # 3. Βρίσκουμε την κίνηση με τη μεγαλύτερη διακύμανση (Max - Min)
        changes = {}
        for action, values in metrics.items():
            if values:
                changes[action] = max(values) - min(values)

        recognized_action = max(changes, key=changes.get)
        return recognized_action, changes[recognized_action]       

    def start_countdown(self):
        """Επαναφέρει το UI και ξεκινά την αντίστροφη μέτρηση."""
        self.is_playing = False
        self.video_label.configure(image="") # Καθαρισμός οθόνης
        self.approval_frame.pack_forget()
        self.mapping_frame.pack_forget()
        self.countdown(3)

    def countdown(self, count):
        """Αναδρομική συνάρτηση για το 3... 2... 1..."""
        if count > 0:
            self.info_label.configure(text=f"{count}...")
            self.after(1000, self.countdown, count - 1)
        else:
            self.info_label.configure(text="🔴 ΚΑΤΑΓΡΑΦΗ (1 δευτερόλεπτο)...")
            # Σήμα στο main app
            self.parent.recorded_landmarks.clear()
            self.parent.recorded_frames.clear()
            self.parent.is_recording_motion = True 
            
            # Σταματάμε μετά από 1000ms (1 δευτερόλεπτο)
            self.after(1000, self.finish_recording)

    def finish_recording(self):
        """Ολοκλήρωση της καταγραφής και έναρξη του Video Loop."""
        self.parent.is_recording_motion = False
        
        # Αντιγραφή των frames από το κεντρικό app στο τοπικό buffer
        self.playback_frames = self.parent.recorded_frames.copy()
        
        if not self.playback_frames:
            self.info_label.configure(text="Σφάλμα: Δεν καταγράφηκαν frames.")
            self.approval_frame.pack(pady=10)
            return

        self.info_label.configure(text="Έγκριση κίνησης;")
        self.approval_frame.pack(pady=10)

        # Ξεκινάμε την λούπα
        self.is_playing = True
        self.playback_index = 0
        self.play_video_loop()

    def play_video_loop(self):
        """Διαβάζει τα frames από τη μνήμη και τα παίζει σε λούπα (~30 FPS)."""
        if not self.is_playing or not self.playback_frames:
            return

        # Φόρτωση του τρέχοντος frame
        frame = self.playback_frames[self.playback_index]
        img = Image.fromarray(frame)
        
        # Αλλαγή μεγέθους για να χωράει όμορφα στο popup
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(320, 240))
        self.video_label.configure(image=ctk_img)
        self.video_label.image = ctk_img # Αποφυγή garbage collection

        # Αύξηση του index και μηδενισμός αν φτάσει στο τέλος (Loop Effect)
        self.playback_index = (self.playback_index + 1) % len(self.playback_frames)
        
        # Κλήση του εαυτού της σε ~33ms (δηλαδή 30 φορές το δευτερόλεπτο)
        self.after(33, self.play_video_loop)

    def retry_recording(self):
        """Ο χρήστης πάτησε 'Ξανά Καταγραφή'."""
        self.start_countdown()

    def approve_motion(self):
        """Ο χρήστης πάτησε [Ναι]. Σταματάει το loop και ζητάει πλήκτρο."""
        self.is_playing = False # Σταματάει το βίντεο για να μην τρώει πόρους
        self.approval_frame.pack_forget()
        self.info_label.configure(text="Αντιστοίχιση σε Πλήκτρο:")
        self.mapping_frame.pack(pady=10)

    def save_to_db(self):
        """Αποθήκευση στη βάση με Δυναμικό/Προσωποποιημένο Υπολογισμό Ορίου (Threshold)."""
        action = self.action_dropdown.get()
        key = self.key_dropdown.get()
        detected_action, score = self.auto_categorize_movement(self.parent.recorded_landmarks)
        # --- 1. ΥΠΟΛΟΓΙΣΜΟΣ ΠΡΟΣΩΠΙΚΟΥ ΟΡΙΟΥ ΑΠΟ ΤΑ ΚΑΤΑΓΕΓΡΑΜΜΕΝΑ ΚΑΡΕ ---
        if detected_action:
            action = detected_action
            print(f"🧠 Η AI επέλεξε αυτόματα: {action} (Ένταση: {score:.3f})")
            
            # Προαιρετικά: Ενημερώνουμε και το UI για να το βλέπει ο χρήστης
            if hasattr(self, 'action_dropdown'):
                self.action_dropdown.set(action)
        else:
            action = self.action_dropdown.get()
            print("⚠️ Δεν εντοπίστηκε ξεκάθαρη κίνηση, χρήση χειροκίνητης επιλογής.")
            
        
        # --- 1. ΥΠΟΛΟΓΙΣΜΟΣ ΠΡΟΣΩΠΙΚΟΥ ΟΡΙΟΥ ΑΠΟ ΤΑ ΚΑΤΑΓΕΓΡΑΜΜΕΝΑ ΚΑΡΕ ---
        personal_threshold = 0.05 # Προεπιλογή ασφαλείας
        
        if hasattr(self.parent, 'recorded_landmarks') and self.parent.recorded_landmarks:
            metrics = []
            import math # Σιγουρευόμαστε ότι είναι διαθέσιμο
            
            # Σαρώνουμε τα ~30 frames που καταγράφηκαν σε αυτό το 1 δευτερόλεπτο
            for face_landmarks in self.parent.recorded_landmarks:
                landmarks = face_landmarks.landmark
                
                if action == "mouth_open":
                    dist = math.hypot(landmarks[13].x - landmarks[14].x, landmarks[13].y - landmarks[14].y)
                    metrics.append(dist)
                elif action == "smile":
                    dist = math.hypot(landmarks[61].x - landmarks[291].x, landmarks[61].y - landmarks[291].y)
                    metrics.append(dist)
                elif action == "left_eye_blink":
                    dist = math.hypot(landmarks[159].x - landmarks[145].x, landmarks[159].y - landmarks[145].y)
                    metrics.append(dist)
                elif action == "right_eye_blink":
                    dist = math.hypot(landmarks[386].x - landmarks[374].x, landmarks[386].y - landmarks[374].y)
                    metrics.append(dist)

            # Εξαγωγή του Ορίου βάσει των ικανοτήτων του χρήστη
            if metrics:
                if action in ["mouth_open", "smile"]:
                    # Θέλουμε τη ΜΕΓΙΣΤΗ απόσταση που πέτυχε ο χρήστης
                    max_dist = max(metrics)
                    # Το όριο ενεργοποίησης θα είναι το 70% της μέγιστης προσπάθειάς του 
                    # (για να μην κουράζεται να το φτάνει στο 100% κάθε φορά)
                    personal_threshold = max_dist * 0.70 
                else:
                    # Για τα μάτια, θέλουμε την ΕΛΑΧΙΣΤΗ απόσταση (πλήρες κλείσιμο)
                    min_dist = min(metrics)
                    # Το όριο ενεργοποίησης θα είναι λίγο πάνω από το ελάχιστο, 
                    # ώστε να "πιάνει" το κλείσιμο ακόμα κι αν δεν σφίξει τα βλέφαρα.
                    personal_threshold = min_dist * 1.50
        # ---------------------------------------------------------------------

        try:
            # 2. Αποθήκευση του ΠΡΟΣΩΠΙΚΟΥ πλέον ορίου στη βάση
            self.db.save_mapping(self.profile_id, action, key, personal_threshold)
            print(f"ΕΠΙΤΥΧΙΑ: Καταχωρήθηκε {action} -> {key} (Personal Threshold: {personal_threshold:.4f})")
            
            if hasattr(self.parent, 'refresh_active_mappings'):
                self.parent.refresh_active_mappings()
                
            self.on_close()
            
        except Exception as e:
            print(f"❌ ΣΦΑΛΜΑ κατά την αποθήκευση: {e}")
            self.info_label.configure(text="Σφάλμα! Δείτε το τερματικό.", text_color="red")

    def on_close(self):
        """Κλείνει το παράθυρο με ασφάλεια."""
        self.is_playing = False
        self.destroy()

class MappingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, profile_id, db):
        super().__init__(parent)
        self.title(f"Καταχωρημένες Κινήσεις - Προφίλ {profile_id}")
        self.geometry("400x400")
        self.attributes("-topmost", True)
        self.db = db
        self.profile_id = profile_id
        self.parent = parent

        ctk.CTkLabel(self, text="Ενεργές Αντιστοιχίσεις", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)

        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.pack(expand=True, fill="both", padx=20, pady=10)

        self.load_mappings()

    def load_mappings(self):
        # Καθαρισμός του frame
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        # Υποθετική μέθοδος db: get_mappings(profile_id) -> list of tuples (id, action, key)
        mappings = self.db.get_mappings(self.profile_id)
        
        if not mappings:
            ctk.CTkLabel(self.scroll_frame, text="Δεν υπάρχουν καταχωρημένες κινήσεις.").pack(pady=20)
            return

        for m_id, action, key in mappings:
            row_frame = ctk.CTkFrame(self.scroll_frame)
            row_frame.pack(fill="x", pady=5)
            
            lbl = ctk.CTkLabel(row_frame, text=f"👉 {action}  ->  [{key.upper()}]", font=ctk.CTkFont(size=14))
            lbl.pack(side="left", padx=10, pady=10)
            
            btn_delete = ctk.CTkButton(row_frame, text="Διαγραφή", width=60, fg_color="#b22222", 
                                       command=lambda i=m_id: self.delete_mapping(i))
            btn_delete.pack(side="right", padx=10)

    def delete_mapping(self, mapping_id):
        self.db.delete_mapping(mapping_id)
        self.load_mappings()
        self.parent.refresh_active_mappings() # Ανανέωση στο κεντρικό loop

class SmartControllerApp(ctk.CTk):
    def refresh_active_mappings(self):
        """Διαβάζει τα mappings από τη βάση και τα αποθηκεύει στη μνήμη."""
        mappings = self.db.get_mappings(self.current_profile_id)
        self.active_mappings.clear()
        
        for m_id, action, key, threshold in mappings:
            # Αποθηκεύουμε το πλήκτρο ΚΑΙ το όριο ευαισθησίας για κάθε κίνηση
            self.active_mappings[action] = {"key": key, "threshold": threshold}
            
        print(f"Ενεργά Mappings ανανεώθηκαν: {self.active_mappings}")
    def __init__(self):
        # --- Μεταβλητές Ελέγχου PyDirectInput ---
        self.active_mappings = {}  # π.χ. {"mouth_open": "space"}
        self.pressed_keys = set()  # Κρατάει τα πλήκτρα που είναι "πατημένα" (held down)
        # --- Μεταβλητές Καταγραφής Κίνησης ---
        self.is_recording_motion = False
        self.recorded_landmarks = []
        self.recorded_frames = [] # [ΝΕΟ] Εδώ θα αποθηκεύονται οι εικόνες (raw frames)
        super().__init__()

        self.title("Smart Controller - Σχεδίαση & Υλοποίηση")
        self.geometry("1100x700")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.db = DBManager()
        self.current_profile_id = 1
        
        # --- MediaPipe Setup ---
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True, 
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles

        # --- Παράμετροι Ποντικιού & Dwell Clicking ---
        self.screen_w, self.screen_h = pydirectinput.size()
        
        # 1. ΑΛΛΑΓΗ: Το Head Tracking ξεκινάει αυτόματα ενεργό!
        self.mouse_control_active = True 
        
        # 2. ΝΕΟ: Μεταβλητές για το Physical Mouse Override
        self.mouse_pause_until = 0.0      
        self.last_injected_pos = None     

        # Εξομάλυνση κίνησης (Smoothing)
        self.smooth_x, self.smooth_y = self.screen_w // 2, self.screen_h // 2
        
        # Μεταβλητές Dwell Click (Οι δικές σου)
        self.dwell_start_time = time.time()
        self.last_cursor_x, self.last_cursor_y = 0, 0
        self.dwell_threshold = 30  # Ανεκτά όρια (pixels) για να θεωρηθεί "ακίνητο" το ποντίκι
        self.dwell_duration = 2.0  # Δευτερόλεπτα
        self.is_dwelling = False

        # 3. ΝΕΟ: Μεταβλητές για τις κινήσεις (Gestures)
        self.active_mappings = {}
        self.pressed_keys = set()

        self._build_ui()
        self.load_profile_data(1)

        # 4. Μεταβλητή για το κλικ με τα φρύδια
        self.is_eyebrow_clicked = False
        
        # --- OpenCV Setup (ΠΡΕΠΕΙ να μπει πριν το update_video) ---
        self.cap = cv2.VideoCapture(0)
        self.cap.set(3, 640) 
        self.cap.set(4, 480)

        self._build_ui()
        self.load_profile_data(1)
        self.update_video()

    def _build_ui(self):
        """Κατασκευάζει το User Interface με μεγάλα στοιχεία για Accessibility."""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 1. Κοινές, μεγάλες γραμματοσειρές για εύκολη ανάγνωση
        large_font = ctk.CTkFont(family="Arial", size=18, weight="bold")
        title_font = ctk.CTkFont(family="Arial", size=24, weight="bold")

        # -- Sidebar --
        # 2. Αυξάνουμε το πλάτος του sidebar (από 250 σε 320) για να χωράνε άνετα τα μεγάλα κουμπιά
        self.sidebar = ctk.CTkFrame(self, width=320, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        ctk.CTkLabel(self.sidebar, text="Smart Controller", font=title_font).pack(pady=30)

        # Προφίλ (Αυξάνουμε το μέγεθος και στα tabs)
        ctk.CTkLabel(self.sidebar, text="Επιλογή Προφίλ:", font=large_font).pack(pady=(10, 5))
        
        self.profile_selector = ctk.CTkSegmentedButton(self.sidebar, values=["1", "2", "3", "4", "5"], 
                                                       font=large_font, height=45,
                                                       command=self.change_profile) # <--- ΕΔΩ ΜΠΗΚΕ Η ΣΥΝΔΕΣΗ
                                                       
        self.profile_selector.set("1")
        # Το fill="x" τα κάνει να πιάνουν όλο το διαθέσιμο οριζόντιο χώρο
        self.profile_selector.pack(pady=10, padx=20, fill="x")

        # Ευαισθησία
        ctk.CTkLabel(self.sidebar, text="Ευαισθησία:", font=large_font).pack(pady=(30, 5))
        # 3. Πιο παχύς slider με μεγαλύτερη "μπίλια" (button_length) για πιο εύκολη στόχευση
        self.sens_slider = ctk.CTkSlider(self.sidebar, from_=0.1, to=3.0, number_of_steps=29, 
                                         command=self.update_sens_label, 
                                         height=25, button_length=25) 
        self.sens_slider.set(1.0)
        self.sens_slider.pack(pady=10, padx=20, fill="x")
        self.sens_value_label = ctk.CTkLabel(self.sidebar, text="1.0", font=large_font)
        self.sens_value_label.pack()

        # 5. Κουμπί Εισαγωγής Κίνησης (ΤΕΡΑΣΤΙΟ: height=70)
        self.btn_add_motion = ctk.CTkButton(self.sidebar, text="Εισαγωγή Κίνησης", 
                                            font=large_font, height=70, corner_radius=10,
                                            fg_color="#1f538d", 
                                            command=self.add_motion_event)
        self.btn_add_motion.pack(pady=10, padx=20, fill="x")

        # Κουμπί Εμφάνισης Καταχωρημένων
        self.btn_review = ctk.CTkButton(self.sidebar, text="Εμφάνιση Καταχωρημένων", 
                                        font=large_font, height=50, corner_radius=10,
                                        fg_color="#8e44ad", hover_color="#732d91",
                                        command=self.open_review_window)
        self.btn_review.pack(pady=10, padx=20, fill="x")

        # --- Video Area ---
        self.video_frame = ctk.CTkFrame(self, corner_radius=10)
        self.video_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.video_label = ctk.CTkLabel(self.video_frame, text="")
        self.video_label.pack(expand=True, fill="both", padx=10, pady=10)
    # --- Βασικές Λειτουργίες ---
    def toggle_mouse_control(self):
        self.mouse_control_active = not self.mouse_control_active
        if self.mouse_control_active:
            self.btn_toggle_mouse.configure(text="Απενεργοποίηση Ποντικιού", fg_color="green", hover_color="#006400")
            self.dwell_start_time = time.time()
        else:
            self.btn_toggle_mouse.configure(text="Ενεργοποίηση Ποντικιού", fg_color="#b22222", hover_color="#8b0000")

    def change_profile(self, value):
        """Ενημερώνει το ενεργό προφίλ όταν ο χρήστης αλλάζει tab."""
        # 1. Ενημέρωση της κεντρικής μεταβλητής (το value έρχεται ως string, π.χ. "2")
        self.current_profile_id = int(value)
        
        print(f"--- Αλλαγή σε Προφίλ {self.current_profile_id} ---")
        
        # 2. Φόρτωση των ρυθμίσεων (αν έχεις αποθηκεύσει το sensitivity στη βάση)
        # 3. Ανανέωση των mappings στη μνήμη ώστε να πιάνει αμέσως τις σωστές κινήσεις
        self.refresh_active_mappings()

    def load_profile_data(self, profile_id):
        profiles = self.db.get_all_profiles()
        for p in profiles:
            if p[0] == profile_id:
                self.sens_slider.set(p[2])
                self.sens_value_label.configure(text=f"{p[2]:.1f}")
                break

    def update_sens_label(self, value):
        self.sens_value_label.configure(text=f"{value:.1f}")

    # --- Core Video Processing Loop ---
    def update_video(self):
        ret, frame = self.cap.read()
        if ret:
            # 1. Καθρέπτισμα και μετατροπή χρώματος
            frame = cv2.flip(frame, 1)
            # 4 = cv2.COLOR_BGR2RGB
            rgb_frame = cv2.cvtColor(frame, 4)

            # 2. Επεξεργασία με MediaPipe
            results = self.face_mesh.process(rgb_frame)

            if results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    
                    # [ΝΕΟ] Αν η αντίστροφη μέτρηση τελείωσε και καταγράφουμε:
                    if self.is_recording_motion:
                        self.recorded_landmarks.append(face_landmarks)
                        # Κρατάμε ένα καθαρό αντίγραφο του RGB frame πριν ζωγραφιστεί το πλέγμα (προαιρετικά)
                        # ή μετά, ανάλογα αν θες να βλέπει το mesh στο loop. 
                        # Εδώ το αποθηκεύουμε όπως είναι εκείνη τη στιγμή.
                        self.recorded_frames.append(rgb_frame.copy())

                    # Α. Σχεδίαση του Mesh στο πρόσωπο
                    self.mp_drawing.draw_landmarks(
                        image=rgb_frame,
                        landmark_list=face_landmarks,
                        connections=self.mp_face_mesh.FACEMESH_TESSELATION,
                        landmark_drawing_spec=None,
                        connection_drawing_spec=self.mp_drawing_styles.get_default_face_mesh_tesselation_style()
                    )

                    # Β. Head Tracking (Χρήση της άκρης της μύτης - Landmark 1)
                    nose_x = face_landmarks.landmark[1].x
                    nose_y = face_landmarks.landmark[1].y

                    # Χρήση του sensitivity από το slider
                    sensitivity = self.sens_slider.get()

                    # Μετατροπή σε συντεταγμένες οθόνης
                    target_x = (nose_x - 0.5) * self.screen_w * sensitivity + (self.screen_w / 2)
                    target_y = (nose_y - 0.5) * self.screen_h * sensitivity + (self.screen_h / 2)

                    # Περιορισμός εντός οθόνης
                    target_x = max(0, min(self.screen_w - 1, target_x))
                    target_y = max(0, min(self.screen_h - 1, target_y))

                    # Εξομάλυνση
                    alpha = 0.2
                    self.smooth_x = self.smooth_x + alpha * (target_x - self.smooth_x)
                    self.smooth_y = self.smooth_y + alpha * (target_y - self.smooth_y)

                    current_x, current_y = int(self.smooth_x), int(self.smooth_y)

                    # ---------------------------------------------------------
                    # Γ. Έλεγχος Ποντικιού, Dwell Clicking & MOUSE OVERRIDE
                    # ---------------------------------------------------------
                    if self.mouse_control_active:
                        import time
                        current_time = time.time()
                        
                        # 1. Υπολογισμός Συντεταγμένων από τη Μύτη (Landmark 4)
                        screen_w, screen_h = pyautogui.size()
                        nose = face_landmarks.landmark[4]
                        
                        # Το x αφαιρείται από το 1 (1 - x) επειδή η κάμερα λειτουργεί σαν καθρέφτης
                        current_x = int(nose.x * screen_w)
                        current_y = int(nose.y * screen_h)
                        
                        # 2. Έλεγχος Physical Mouse Override
                        actual_mouse_x, actual_mouse_y = pyautogui.position()
                        
                        if self.last_injected_pos is not None:
                            dist_moved = math.hypot(actual_mouse_x - self.last_injected_pos[0], actual_mouse_y - self.last_injected_pos[1])
                            
                            # Αυξήσαμε την ανοχή στο 25. Αν μετακινηθεί >25 pixels από εξωτερικό ποντίκι, μπαίνει σε παύση
                            if dist_moved > 25:
                                self.mouse_pause_until = current_time + 3.0
                                
                        # 3. Εκτέλεση Head Tracking (Αν δεν είμαστε σε παύση)
                        if current_time >= self.mouse_pause_until:
                            pydirectinput.moveTo(current_x, current_y)
                            self.last_injected_pos = (current_x, current_y)
                            
                            # ---------------------------------------------------------
                            # ΝΕΟ: Κλικ με Ανασήκωμα Φρυδιών / Γούρλωμα Ματιών
                            # ---------------------------------------------------------
                            landmarks = face_landmarks.landmark
                            # Υπολογίζουμε την απόσταση μεταξύ φρυδιού και ματιού (αριστερά και δεξιά)
                            # 105: Αριστερό φρύδι, 159: Αριστερό άνω βλέφαρο
                            # 336: Δεξί φρύδι, 386: Δεξί άνω βλέφαρο
                            left_eyebrow_dist = math.hypot(landmarks[105].x - landmarks[159].x, landmarks[105].y - landmarks[159].y)
                            right_eyebrow_dist = math.hypot(landmarks[336].x - landmarks[386].x, landmarks[336].y - landmarks[386].y)
                            
                            # Παίρνουμε τον μέσο όρο και των δύο ματιών για μεγαλύτερη ακρίβεια
                            avg_eyebrow_dist = (left_eyebrow_dist + right_eyebrow_dist) / 2
                            
                            # Το όριο (Threshold). Αν δεις ότι δυσκολεύεσαι να κάνεις κλικ, 
                            # κάνε αυτό το νούμερο μικρότερο (π.χ. 0.035). Αν κάνει κλικ μόνο του, κάν' το μεγαλύτερο (π.χ. 0.045).
                            eyebrow_threshold = 0.055 
                            
                            if avg_eyebrow_dist > eyebrow_threshold:
                                # Αν τα φρύδια είναι σηκωμένα και ΔΕΝ έχουμε ήδη κάνει κλικ
                                if not self.is_eyebrow_clicked:
                                    pydirectinput.click()
                                    self.is_eyebrow_clicked = True
                                    print(f"🖱️ [CLICK] Φρύδια σηκώθηκαν! (Απόσταση: {avg_eyebrow_dist:.3f})")
                                    cv2.putText(rgb_frame, "CLICK!", (10, 70), 0, 1.5, (0, 255, 0), 3)
                            else:
                                # Αν τα φρύδια κατέβηκαν, επαναφέρουμε τον διακόπτη
                                self.is_eyebrow_clicked = False
                                
                        else:
                            # 4. Κατάσταση Παύσης (Pause Mode)
                            self.last_injected_pos = (actual_mouse_x, actual_mouse_y)
                            remaining_time = self.mouse_pause_until - current_time
                            cv2.putText(rgb_frame, f"MOUSE OVERRIDE: {remaining_time:.1f}s", (10, 30), 0, 1, (0, 0, 255), 2)
                        # ---------------------------------------------------------
                        # Δ. Έλεγχος Κινήσεων Προσώπου (Gestures to Keys)
                        # ---------------------------------------------------------
                        try:
                            # 1. Υπολογισμός και των 10 αποστάσεων ζωντανά
                            if face_landmarks:
                                landmarks = face_landmarks.landmark
                                current_metrics = {
                                    "mouth_open": math.hypot(landmarks[13].x - landmarks[14].x, landmarks[13].y - landmarks[14].y),
                                    "smile": math.hypot(landmarks[61].x - landmarks[291].x, landmarks[61].y - landmarks[291].y),
                                    "eyebrows_up": (math.hypot(landmarks[105].x - landmarks[159].x, landmarks[105].y - landmarks[159].y) + math.hypot(landmarks[336].x - landmarks[386].x, landmarks[336].y - landmarks[386].y)) / 2,
                                    "left_eye_blink": math.hypot(landmarks[159].x - landmarks[145].x, landmarks[159].y - landmarks[145].y),
                                    "right_eye_blink": math.hypot(landmarks[386].x - landmarks[374].x, landmarks[386].y - landmarks[374].y),
                                    "kiss": math.hypot(landmarks[61].x - landmarks[291].x, landmarks[61].y - landmarks[291].y),
                                    "jaw_left": math.hypot(landmarks[152].x - landmarks[132].x, landmarks[152].y - landmarks[132].y),
                                    "jaw_right": math.hypot(landmarks[152].x - landmarks[361].x, landmarks[152].y - landmarks[361].y),
                                    "nose_scrunch": math.hypot(landmarks[1].x - landmarks[13].x, landmarks[1].y - landmarks[13].y),
                                    "cheek_puff": math.hypot(landmarks[50].x - landmarks[280].x, landmarks[50].y - landmarks[280].y)
                                }

                                # 2. Δυναμικός Έλεγχος
                                for action, data in self.active_mappings.items():
                                    target_key = data["key"]
                                    threshold = data["threshold"]
                                    
                                    if action not in current_metrics:
                                        continue
                                        
                                    is_active = False
                                    
                                    # ΟΜΑΔΑ 1: Ενεργοποιούνται όταν η απόσταση ΜΕΓΑΛΩΝΕΙ
                                    if action in ["mouth_open", "smile", "eyebrows_up", "cheek_puff"]:
                                        is_active = current_metrics[action] > threshold
                                        
                                    # ΟΜΑΔΑ 2: Ενεργοποιούνται όταν η απόσταση ΜΙΚΡΑΙΝΕΙ
                                    elif action in ["left_eye_blink", "right_eye_blink", "kiss", "jaw_left", "jaw_right", "nose_scrunch"]:
                                        is_active = current_metrics[action] < threshold

                                    # 3. Εντολές στο PyDirectInput
                                    if is_active:
                                        if target_key not in self.pressed_keys:
                                            pydirectinput.keyDown(target_key)
                                            self.pressed_keys.add(target_key)
                                            print(f"🟢 [ΕΝΕΡΓΟ] {action} -> Πατήθηκε: {target_key.upper()}")
                                    else:
                                        if target_key in self.pressed_keys:
                                            pydirectinput.keyUp(target_key)
                                            self.pressed_keys.remove(target_key)
                                            print(f"🔴 [ΑΝΕΝΕΡΓΟ] {action} -> Απελευθερώθηκε: {target_key.upper()}")
                                            
                        except Exception as e:
                            print(f"❌ ΣΦΑΛΜΑ ΣΤΑ GESTURES: {e}")

            # 3. Μετατροπή και Εμφάνιση στο GUI
            img = Image.fromarray(rgb_frame)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(640, 480))
            self.video_label.configure(image=ctk_img)
            self.video_label.image = ctk_img

        self.after(10, self.update_video)

    def add_motion_event(self):
        # Δημιουργία και εμφάνιση του Popup παραθύρου
        popup = MotionRegistrationWindow(self, self.current_profile_id, self.db)
        popup.grab_set() # "Κλειδώνει" την εστίαση στο popup μέχρι να κλείσει

    def open_review_window(self):
        review_popup = ProfileReviewWindow(self, self.current_profile_id, self.db)
        review_popup.grab_set()

    def on_closing(self):
        self.cap.release()
        self.destroy()

if __name__ == "__main__":
    app = SmartControllerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()