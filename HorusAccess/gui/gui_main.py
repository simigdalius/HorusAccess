import customtkinter as ctk
import cv2
import mediapipe as mp
# Προσθήκη των συγκεκριμένων modules για να μην ψάχνει το 'solutions' μετά
from mediapipe.python.solutions import face_mesh as face_mesh_lib
from mediapipe.python.solutions import drawing_utils as drawing_utils_lib
from mediapipe.python.solutions import drawing_styles as drawing_styles_lib

from PIL import Image
import pydirectinput
import time
import math
import os
import sys
from database.db_manager import DBManager


from database.db_manager import DBManager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Απενεργοποίηση του FailSafe για να μην κρασάρει αν το ποντίκι πάει στις γωνίες
pydirectinput.FAILSAFE = False

class MotionRegistrationWindow(ctk.CTkToplevel):
    def __init__(self, parent, current_profile_id, db):
        super().__init__(parent)
        self.parent = parent
        self.profile_id = current_profile_id
        self.db = db

        # Ρυθμίσεις παραθύρου
        self.title("Εισαγωγή Κίνησης")
        self.geometry("450x350")
        self.attributes("-topmost", True) # Κρατάει το popup πάντα μπροστά
        self.resizable(False, False)

        # --- UI Στοιχεία ---
        self.info_label = ctk.CTkLabel(self, text="Ετοιμαστείτε...", font=ctk.CTkFont(size=22, weight="bold"))
        self.info_label.pack(pady=40)

        # Frame για τα κουμπιά Έγκρισης (Αρχικά κρυμμένο)
        self.approval_frame = ctk.CTkFrame(self, fg_color="transparent")
        
        self.btn_yes = ctk.CTkButton(self.approval_frame, text="Ναι", fg_color="green", hover_color="#006400", command=self.approve_motion)
        self.btn_yes.grid(row=0, column=0, padx=10)
        
        self.btn_no = ctk.CTkButton(self.approval_frame, text="Ξανά Καταγραφή", fg_color="#b22222", hover_color="#8b0000", command=self.start_countdown)
        self.btn_no.grid(row=0, column=1, padx=10)

        # Frame για την Αντιστοίχιση Πλήκτρου (Αρχικά κρυμμένο)
        self.mapping_frame = ctk.CTkFrame(self, fg_color="transparent")

        # Λίστα με τις πιθανές κινήσεις που θέλουμε να αναγνωρίζουμε
        ctk.CTkLabel(self.mapping_frame, text="Όνομα Κίνησης:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        self.action_dropdown = ctk.CTkOptionMenu(self.mapping_frame, values=["mouth_open", "left_eye_blink", "right_eye_blink", "eyebrows_up", "smile"])
        self.action_dropdown.grid(row=0, column=1, padx=10, pady=10)

        # Λίστα με τα διαθέσιμα πλήκτρα
        ctk.CTkLabel(self.mapping_frame, text="Πλήκτρο:").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        self.key_dropdown = ctk.CTkOptionMenu(self.mapping_frame, values=["space", "enter", "w", "a", "s", "d", "left_click", "right_click"])
        self.key_dropdown.grid(row=1, column=1, padx=10, pady=10)

        self.btn_save = ctk.CTkButton(self.mapping_frame, text="Αποθήκευση στο Προφίλ", command=self.save_to_db)
        self.btn_save.grid(row=2, column=0, columnspan=2, pady=20)

        # Ξεκινάμε την αντίστροφη μέτρηση αυτόματα μόλις ανοίξει το παράθυρο
        self.start_countdown()

    def start_countdown(self):
        """Επαναφέρει το UI και ξεκινά την αντίστροφη μέτρηση."""
        self.approval_frame.pack_forget()
        self.mapping_frame.pack_forget()
        self.countdown(3)

    def countdown(self, count):
        """Αναδρομική συνάρτηση για το 3... 2... 1..."""
        if count > 0:
            self.info_label.configure(text=f"{count}...")
            self.after(1000, self.countdown, count - 1)
        else:
            self.info_label.configure(text="🔴 ΚΑΤΑΓΡΑΦΗ ΔΕΔΟΜΕΝΩΝ...")
            # Δίνουμε σήμα στο κεντρικό app να ξεκινήσει τη συλλογή MediaPipe landmarks
            self.parent.is_recording_motion = True 
            self.parent.recorded_landmarks.clear() # Καθαρίζουμε παλιά δεδομένα
            
            # Περιμένουμε 1 δευτερόλεπτο και σταματάμε
            self.after(1000, self.finish_recording)

    def finish_recording(self):
        """Ολοκλήρωση του 1 δευτερολέπτου καταγραφής."""
        self.parent.is_recording_motion = False
        
        # Εδώ στη διπλωματική σου θα μπορούσες να πάρεις τα δεδομένα από το self.parent.recorded_landmarks 
        # για να εκπαιδεύσεις ένα μοντέλο (π.χ. SVM) ή να βρεις τον μέσο όρο των αποστάσεων.
        print(f"Συλλέχθηκαν δεδομένα από {len(self.parent.recorded_landmarks)} frames.")

        self.info_label.configure(text="Έγκριση κίνησης;")
        self.approval_frame.pack(pady=20)

    def approve_motion(self):
        """Ο χρήστης πάτησε [Ναι]. Εμφάνιση του μενού αντιστοίχισης."""
        self.approval_frame.pack_forget()
        self.info_label.configure(text="Αντιστοίχιση σε Πλήκτρο:")
        self.mapping_frame.pack(pady=10)

    def save_to_db(self):
        """Αποθήκευση στη βάση SQLite μέσω του db_manager."""
        action = self.action_dropdown.get()
        key = self.key_dropdown.get()
        
        # Αποθήκευση με χρήση της υπάρχουσας μεθόδου του db_manager
        self.db.save_mapping(self.profile_id, action, key)
        print(f"Επιτυχής αποθήκευση: Προφίλ {self.profile_id} | {action} -> {key}")
        
        # Κλείσιμο του popup
        self.destroy()

class SmartControllerApp(ctk.CTk):
    def __init__(self):
        # --- Μεταβλητές Καταγραφής Κίνησης ---
        self.is_recording_motion = False
        self.recorded_landmarks = []
        super().__init__()

        self.title("Smart Controller - Σχεδίαση & Υλοποίηση")
        self.geometry("1100x700")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.db = DBManager()
        self.current_profile_id = 1
        
        # --- MediaPipe Setup (Εναλλακτικός τρόπος φόρτωσης) ---

        self.mp_face_mesh = face_mesh_lib
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True, 
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = drawing_utils_lib
        self.mp_drawing_styles = drawing_styles_lib

        # --- Παράμετροι Ποντικιού & Dwell Clicking ---
        self.screen_w, self.screen_h = pydirectinput.size()
        self.mouse_control_active = False # Διακόπτης ασφαλείας
        
        # Εξομάλυνση κίνησης (Smoothing)
        self.smooth_x, self.smooth_y = self.screen_w // 2, self.screen_h // 2
        
        # Μεταβλητές Dwell Click
        self.dwell_start_time = time.time()
        self.last_cursor_x, self.last_cursor_y = 0, 0
        self.dwell_threshold = 30  # Ανεκτά όρια (pixels) για να θεωρηθεί "ακίνητο" το ποντίκι
        self.dwell_duration = 2.0  # Δευτερόλεπτα
        self.is_dwelling = False

        # --- OpenCV Setup ---
        self.cap = cv2.VideoCapture(0)
        # Χρήση αριθμών αντί για σταθερές cv2 για αποφυγή false errors στο VS Code
        self.cap.set(3, 640) # 3 = cv2.CAP_PROP_FRAME_WIDTH
        self.cap.set(4, 480) # 4 = cv2.CAP_PROP_FRAME_HEIGHT

        self._build_ui()
        self.load_profile_data(1)
        self.update_video()

    def _build_ui(self):

        # Κουμπί για νέα κίνηση
        self.btn_add_motion = ctk.CTkButton(self.sidebar, text="Εισαγωγή Κίνησης", 
                                            fg_color="#1f538d", 
                                            command=self.add_motion_event)
        self.btn_add_motion.pack(pady=10, padx=20)
        """Κατασκευάζει το User Interface."""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # -- Sidebar --
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        ctk.CTkLabel(self.sidebar, text="Smart Controller", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)

        # Προφίλ
        self.profile_selector = ctk.CTkSegmentedButton(self.sidebar, values=["1", "2", "3", "4", "5"], command=self.change_profile)
        self.profile_selector.set("1")
        self.profile_selector.pack(pady=10, padx=10)

        # Ευαισθησία
        ctk.CTkLabel(self.sidebar, text="Ευαισθησία (Sensitivity):").pack(pady=(20, 0))
        self.sens_slider = ctk.CTkSlider(self.sidebar, from_=0.1, to=3.0, number_of_steps=29, command=self.update_sens_label)
        self.sens_slider.set(1.0)
        self.sens_slider.pack(pady=10, padx=10)
        self.sens_value_label = ctk.CTkLabel(self.sidebar, text="1.0")
        self.sens_value_label.pack()

        # Κουμπί Ενεργοποίησης Ποντικιού (CRITICAL για testing)
        self.btn_toggle_mouse = ctk.CTkButton(self.sidebar, text="Ενεργοποίηση Ποντικιού", 
                                              fg_color="#b22222", hover_color="#8b0000",
                                              command=self.toggle_mouse_control)
        self.btn_toggle_mouse.pack(pady=20, padx=20)

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
        self.current_profile_id = int(value)
        self.load_profile_data(self.current_profile_id)

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
                    
                    # [ΝΕΟ] Αν η αντίστροφη μέτρηση τελείωσε και είμαστε στο 1 δευτερόλεπτο καταγραφής:
                    if self.is_recording_motion:
                        # Αποθηκεύουμε τα raw δεδομένα του frame σε μια λίστα
                        self.recorded_landmarks.append(face_landmarks)

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

                    # Γ. Έλεγχος Ποντικιού και Dwell Clicking
                    if self.mouse_control_active:
                        pydirectinput.moveTo(current_x, current_y)

                        dist = math.hypot(current_x - self.last_cursor_x, current_y - self.last_cursor_y)

                        if dist < self.dwell_threshold:
                            elapsed_time = time.time() - self.dwell_start_time
                            self.is_dwelling = True
                            
                            # 0 = cv2.FONT_HERSHEY_SIMPLEX
                            cv2.putText(rgb_frame, f"Dwell: {elapsed_time:.1f}s", (10, 30), 
                                        0, 1, (255, 0, 0), 2)

                            if elapsed_time >= self.dwell_duration:
                                pydirectinput.click()
                                print("--- Dwell Click Ενεργοποιήθηκε ---")
                                
                                # 0 = cv2.FONT_HERSHEY_SIMPLEX
                                cv2.putText(rgb_frame, "CLICK!", (10, 70), 0, 1.5, (0, 255, 0), 3)
                                
                                self.dwell_start_time = time.time()
                        else:
                            self.is_dwelling = False
                            self.dwell_start_time = time.time()
                            self.last_cursor_x = current_x
                            self.last_cursor_y = current_y

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

    def on_closing(self):
        self.cap.release()
        self.destroy()

if __name__ == "__main__":
    app = SmartControllerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()