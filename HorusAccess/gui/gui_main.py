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
import json
import ollama
import glob
import winshell 
import io
import requests
from win32com.client import Dispatch
from database.db_manager import DBManager

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def fetch_game_image(game_title, image_url=None, size=(180, 100)):
    """Κατεβάζει την εικόνα του παιχνιδιού. Αν δεν υπάρχει URL, ψάχνει αυτόματα εικόνα βάσει τίτλου."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    # 1. Δοκιμή λήψης από το απευθείας URL αν υπάρχει
    if image_url:
        try:
            res = requests.get(image_url, headers=headers, timeout=3)
            if res.status_code == 200:
                pil_img = Image.open(io.BytesIO(res.content)).convert("RGBA")
                pil_img = pil_img.resize(size, Image.Resampling.LANCZOS)
                return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)
        except Exception:
            pass

    # 2. Fallback: Αυτόματη αναζήτηση εικόνας μέσω Steam API με βάση το όνομα (π.χ. Sonic Mania)
    try:
        search_url = f"https://store.steampowered.com/api/storesearch/?term={requests.utils.quote(game_title)}&l=english&cc=US"
        res = requests.get(search_url, headers=headers, timeout=3)
        if res.status_code == 200:
            data = res.json()
            if data.get("items"):
                app_id = data["items"][0]["id"]
                img_url = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"
                img_res = requests.get(img_url, headers=headers, timeout=3)
                if img_res.status_code == 200:
                    pil_img = Image.open(io.BytesIO(img_res.content)).convert("RGBA")
                    pil_img = pil_img.resize(size, Image.Resampling.LANCZOS)
                    return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)
    except Exception as e:
        print(f"⚠️ Αποτυχία αυτόματης αναζήτησης εικόνας για {game_title}: {e}")

    return None

# horus AI
pydirectinput.FAILSAFE = False
class AutonomousGameSelectorWindow(ctk.CTkToplevel):
    """Παράθυρο πλέγματος που εμφανίζει τα πραγματικά εγκατεστημένα παιχνίδια του PC."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

        self.title("Horus AI - Αυτόνομη Επιλογή Εγκατεστημένων Παιχνιδιών")
        self.geometry("950x700")
        self.configure(fg_color="#111215")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.grab_set()

        # Ανίχνευση πραγματικών παιχνιδιών στο σύστημα
        self.games = self.detect_installed_games()

        self._build_ui()


    def detect_installed_games(self):
        """Ανιχνεύει ΑΠΟΚΛΕΙΣΤΙΚΑ παιχνίδια από Epic Games, Steam, GOG και εξειδικευμένους φακέλους."""
        detected_games = []
        found_names = set()

        # Λίστα αποκλεισμού για συστήματα/εργαλεία που μπορεί να ξεφύγουν από launchers
        ignored_keywords = [
            "opera", "browser", "code", "visual studio", "wps", "office", "word", "excel", 
            "powerpoint", "administration", "tools", "librewolf", "chrome", "firefox", 
            "edge", "discord", "spotify", "vlc", "uninstall", "setup", "help", "python", 
            "git", "node", "cmd", "powershell", "control panel", "settings", "redistributable",
            "steamworks", "proton", "prerequisites", "epic online services"
        ]

        def is_valid_game(name):
            if not name:
                return False
            name_lower = name.lower()
            return not any(ignored in name_lower for ignored in ignored_keywords)

        # ==========================================
        # 1. EPIC GAMES DETECTOR (με εικόνα)
        # ==========================================
        epic_manifest_path = r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"
        if os.path.exists(epic_manifest_path):
            for file in os.listdir(epic_manifest_path):
                if file.endswith(".item"):
                    try:
                        with open(os.path.join(epic_manifest_path, file), "r", encoding="utf-8") as f:
                            data = json.load(f)
                            game_name = data.get("DisplayName")
                            
                            # Λήψη εικόνας από τα μεταδεδομένα της Epic (αν υπάρχει)
                            img_url = None
                            # Για το Sonic Mania / Epic Games fallback URL:
                            if game_name and "Sonic Mania" in game_name:
                                img_url = "https://cdn2.unrealengine.com/egs-sonicmania-sega-s2-1200x1600-244243640.jpg"

                            if game_name and game_name not in found_names and is_valid_game(game_name):
                                found_names.add(game_name)
                                detected_games.append({
                                    "title": game_name,
                                    "platform": "Epic Games",
                                    "image_url": img_url
                                })
                    except Exception:
                        pass

        # ==========================================
        # 2. STEAM DETECTOR (με αυτόματη εικόνα μέσω AppID)
        # ==========================================
        steam_paths = [
            r"C:\Program Files (x86)\Steam\steamapps",
            r"C:\Program Files\Steam\steamapps",
            r"D:\SteamLibrary\steamapps",
            r"E:\SteamLibrary\steamapps",
        ]

        for s_path in steam_paths:
            if os.path.exists(s_path):
                manifests = glob.glob(os.path.join(s_path, "appmanifest_*.acf"))
                for mfile in manifests:
                    try:
                        with open(mfile, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            if '"name"' in content and '"appid"' in content:
                                name_line = [l for l in content.split("\n") if '"name"' in l][0]
                                appid_line = [l for l in content.split("\n") if '"appid"' in l][0]
                                
                                game_name = name_line.split('"')[3]
                                app_id = appid_line.split('"')[3]
                                
                                # Εικόνα εξωφύλλου απευθείας από το CDN του Steam
                                img_url = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"
                                
                                if game_name not in found_names and is_valid_game(game_name):
                                    found_names.add(game_name)
                                    detected_games.append({
                                        "title": game_name,
                                        "platform": "Steam",
                                        "image_url": img_url
                                    })
                    except Exception:
                        pass
        # ==========================================
        # 3. GOG GALAXY DETECTOR (Windows Registry)
        # ==========================================
        try:
            import winreg
            gog_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games")
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(gog_key, i)
                    subkey = winreg.OpenKey(gog_key, subkey_name)
                    game_name, _ = winreg.QueryValueEx(subkey, "gameName")
                    if game_name and game_name not in found_names and is_valid_game(game_name):
                        found_names.add(game_name)
                        detected_games.append({
                            "title": game_name,
                            "platform": "GOG",
                            "genre": "GOG Game"
                        })
                    i += 1
                except OSError:
                    break
        except Exception:
            pass

        # ==========================================
        # 4. ΣΚΑΝΑΡΙΣΜΑ ΜΟΝΟ ΣΤΗΝ ΕΠΙΦΑΝΕΙΑ ΕΡΓΑΣΙΑΣ (Desktop Shortcuts)
        # ==========================================
        # Ψάχνουμε ΜΟΝΟ στο Desktop και ΟΧΙ στο Start Menu/Programs
        desktop_dir = winshell.desktop()
        if os.path.exists(desktop_dir):
            shell = Dispatch("WScript.Shell")
            for file in os.listdir(desktop_dir):
                if file.endswith(".lnk"):
                    shortcut_path = os.path.join(desktop_dir, file)
                    try:
                        target = shell.CreateShortCut(shortcut_path).Targetpath
                        game_name = file.replace(".lnk", "")
                        
                        # Αν δείχνει σε .exe και ΔΕΝ είναι στη λίστα αποκλεισμού
                        if target.endswith(".exe") and is_valid_game(game_name) and game_name not in found_names:
                            found_names.add(game_name)
                            detected_games.append({
                                "title": game_name,
                                "platform": "PC Game",
                                "genre": "Standalone Game"
                            })
                    except Exception:
                        pass

        return detected_games

    def _build_ui(self):
        ctk.CTkLabel(
            self, 
            text="🤖 ΕΓΚΑΤΕΣΤΗΜΕΝΑ ΠΑΙΧΝΙΔΙΑ (Horus AI)", 
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"), 
            text_color="#00f0ff"
        ).pack(pady=(20, 5))

        grid_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True, padx=20, pady=10)
        grid_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="col")

        for index, game in enumerate(self.games):
            row = index // 3
            col = index % 3

            # Κάρτα Παιχνιδιού
            card = ctk.CTkFrame(grid_frame, fg_color="#1f2128", corner_radius=12, border_color="#2b2d35", border_width=1)
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")

            # 1. Προσπάθεια Φόρτωσης Εικόνας (με fallback αναζήτησης τίτλου)
            ctk_img = fetch_game_image(
                game_title=game.get('title', ''), 
                image_url=game.get('image_url'), 
                size=(180, 100)
            )

            if ctk_img:
                img_label = ctk.CTkLabel(card, image=ctk_img, text="")
                img_label.image = ctk_img  # Κράτηση reference για Garbage Collection
                img_label.pack(pady=(10, 5), padx=10)
            else:
                # Fallback εικονίδιο μόνο αν αποτύχουν όλα
                ctk.CTkLabel(card, text="🎮", font=ctk.CTkFont(size=40)).pack(pady=(20, 10))

            # 2. Τίτλος Παιχνιδιού
            ctk.CTkLabel(
                card, 
                text=game.get('title', 'Άγνωστο Παιχνίδι'), 
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color="#ffffff",
                wraplength=180
            ).pack(pady=(5, 2), padx=8)

            # 3. Badge Πλατφόρμας
            ctk.CTkLabel(
                card, 
                text=f"• {game.get('platform', 'PC')} •", 
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color="#00ffaa"
            ).pack(pady=(0, 8))

            # 4. Κουμπί Επιλογής
            btn = ctk.CTkButton(
                card,
                text="Ανάλυση & Επιλογή",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                fg_color="#00f0ff",
                text_color="#111215",
                hover_color="#00ffaa",
                height=30,
                corner_radius=6,
                command=lambda g=game: self.select_game(g)
            )
            btn.pack(pady=(0, 12), padx=12, fill="x")
    
    def select_game(self, game):
        print(f"🤖 [Horus AI] Αναλύονται οι λειτουργίες για: {game['title']}...")
        
        # Έλεγχος αν πρόκειται για Browser/Desktop App
        is_browser = any(b in game['title'].lower() for b in ["opera", "chrome", "edge", "firefox", "browser"])

        # Σύντομες λίστες για να μην μπερδεύεται το μοντέλο
        available_motions = [
            "mouth_open", "smile", "left_eye_blink", "right_eye_blink",
            "eyebrows_up", "eyebrows_frown", "head_up", "head_down", "head_left", "head_right"
        ]

        if is_browser:
            context_instruction = "Η εφαρμογή είναι BROWSER. Χρησιμοποίησε ΜΟΝΟ: left_click, right_click, down, up, enter, space."
        else:
            context_instruction = "Η εφαρμογή είναι ΠΑΙΧΝΙΔΙ. Χρησιμοποίησε GAMING KEYS όπως: w, a, s, d, space, left_click."

        prompt = f"""Task: Create 3 face-to-key mappings for '{game['title']}'.
{context_instruction}

Allowed Motions: {json.dumps(available_motions)}
Allowed Keys: ["w", "a", "s", "d", "space", "enter", "up", "down", "left_click", "right_click"]

Respond strictly in this JSON format:
{{
  "mappings": [
    {{"motion": "mouth_open", "key": "left_click", "description": "Left Click / Select"}},
    {{"motion": "eyebrows_up", "key": "right_click", "description": "Right Click / Menu"}},
    {{"motion": "head_down", "key": "down", "description": "Scroll Down"}}
  ]
}}"""

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
            
            result = json.loads(response['message']['content'])
            mappings = result.get("mappings", [])

        except Exception as e:
            print(f"⚠️ Σφάλμα απόκρισης Ollama: {e}")

        # --- FALLBACK / SAFETY NET ---
        # Αν το LLM επέστρεψε κενή λίστα, φτιάχνουμε αυτόματα λογικά defaults
        if not mappings:
            print("⚠️ Το LLM δεν επέστρεψε mappings. Εφαρμογή έξυπνου Fallback...")
            if is_browser:
                mappings = [
                    {"motion": "mouth_open", "key": "left_click", "description": "Αριστερό Κλικ (Επιλογή)"},
                    {"motion": "eyebrows_up", "key": "right_click", "description": "Δεξί Κλικ (Μενού)"},
                    {"motion": "head_down", "key": "down", "description": "Scroll Down"},
                    {"motion": "head_up", "key": "up", "description": "Scroll Up"}
                ]
            else:
                mappings = [
                    {"motion": "mouth_open", "key": "space", "description": "Jump / Action"},
                    {"motion": "head_up", "key": "w", "description": "Move Forward"},
                    {"motion": "head_left", "key": "a", "description": "Move Left"},
                    {"motion": "head_right", "key": "d", "description": "Move Right"}
                ]

        # 1. Εύρεση του πρώτου κενού (null) προφίλ (από 1 έως 5)
        target_profile = 1
        if hasattr(self.parent, 'db'):
            for p_id in range(1, 6):
                existing = self.parent.db.get_mappings(p_id)
                if not existing:
                    target_profile = p_id
                    break

        # 2. Εμφάνιση παραθύρου επιβεβαίωσης
        self.show_confirmation_dialog(game['title'], mappings, target_profile)
    
    def show_confirmation_dialog(self, game_title, mappings, target_profile):
        """Εμφανίζει παράθυρο με τις προτάσεις του Horus AI και περιμένει επιβεβαίωση (OK)."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Πρόταση Horus AI")
        dialog.geometry("550x480")
        dialog.configure(fg_color="#111215")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        # Τίτλος
        ctk.CTkLabel(
            dialog, 
            text="🤖 ΤΟ HORUS AI ΠΡΟΤΕΙΝΕΙ:", 
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), 
            text_color="#00f0ff"
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            dialog, 
            text=f"Παιχνίδι: {game_title}\nΘα γίνει αποθήκευση στο Προφίλ {target_profile}", 
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), 
            text_color="#00ffaa"
        ).pack(pady=(0, 15))

        # Λίστα προτεινόμενων controls
        scroll_frame = ctk.CTkScrollableFrame(dialog, fg_color="#1f2128", height=220)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=5)

        for m in mappings:
            row_str = f"• {m['motion']} ➔ [{m['key'].upper()}] ({m.get('description', '')})"
            ctk.CTkLabel(
                scroll_frame, 
                text=row_str, 
                font=ctk.CTkFont(family="Segoe UI", size=14), 
                text_color="#ffffff",
                anchor="w"
            ).pack(fill="x", pady=4, padx=10)

        # Συνάρτηση που εκτελείται όταν πατηθεί το OK
        def confirm_and_save():
            if hasattr(self.parent, 'db'):
                # 1. Αποθήκευση των mappings
                for item in mappings:
                    self.parent.db.save_mapping(
                        profile_id=target_profile,
                        action=item["motion"],
                        mapped_key=item["key"]
                    )
                
                # 2. Αποθήκευση της περιγραφής/ονόματος της εφαρμογής για το προφίλ
                if hasattr(self.parent.db, 'update_profile_name'):
                    self.parent.db.update_profile_name(target_profile, f"Προφίλ {target_profile} ({game_title})")
                
                print(f"💾 Επιτυχής αποθήκευση για την εφαρμογή '{game_title}' στο Προφίλ {target_profile}!")
                
                # 3. Ενημέρωση του UI της εφαρμογής
                if hasattr(self.parent, 'profile_selector'):
                    self.parent.profile_selector.set(str(target_profile))
                if hasattr(self.parent, 'change_profile'):
                    self.parent.change_profile(str(target_profile))

            dialog.grab_release()
            dialog.destroy()
            self.grab_release()
            self.destroy()

        # Κουμπί OK
        btn_ok = ctk.CTkButton(
            dialog,
            text="OK (Αποδοχή & Αποθήκευση)",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            height=45,
            fg_color="#00ffaa",
            text_color="#111215",
            hover_color="#00f0ff",
            command=confirm_and_save
        )
        btn_ok.pack(pady=20, padx=20, fill="x")



class ProfileReviewWindow(ctk.CTkToplevel):
    def __init__(self, parent, current_profile_id, db):
        super().__init__(parent)
        
        self.parent = parent
        self.profile_id = current_profile_id
        self.db = db

        self.title(f"Διαχείριση Καταχωρημένων (Προφίλ {self.profile_id})")
        self.geometry("750x550")
        self.attributes("-topmost", True)

        self.row_widgets = {} 
        self._build_ui()
        self.load_data()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Διαχείριση Κινήσεων", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=20)

        self.scroll_frame = ctk.CTkScrollableFrame(self, width=680, height=420)
        self.scroll_frame.pack(pady=10, padx=20, fill="both", expand=True)

    # ---> ΕΔΩ ΜΠΑΙΝΕΙ Η ΝΕΑ load_data() ΠΟΥ ΕΓΡΑΨΑ ΠΑΝΩ <---

    def delete_entry(self, mapping_id):
        self.db.delete_mapping(mapping_id)
        print(f" Διαγράφηκε η κίνηση με ID {mapping_id}")
        self.load_data()
        if hasattr(self.parent, 'refresh_active_mappings'):
            self.parent.refresh_active_mappings()



class ProfileReviewWindow(ctk.CTkToplevel):
    def __init__(self, parent, current_profile_id, db):
        super().__init__(parent)
        
        self.parent = parent
        self.profile_id = current_profile_id
        self.db = db

        self.title(f"Εμφάνιση & Επεξεργασία Καταχωρημένων (Προφίλ {self.profile_id})")
        self.geometry("750x550")
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
            # Fallback αν το κρατάμε στη μνήμη του parent
            profile_name = f"Προφίλ {self.profile_id} - {self.parent.profile_games[self.profile_id]}"

        # 2. Εμφάνιση Τίτλου
        ctk.CTkLabel(
            self, 
            text=f"Διαχείριση Κινήσεων\n({profile_name})", 
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#00f0ff"
        ).pack(pady=15)

        self.scroll_frame = ctk.CTkScrollableFrame(self, width=680, height=400)
        self.scroll_frame.pack(pady=10, padx=20, fill="both", expand=True)

    def load_data(self):
        """Φορτώνει τα mappings σε 3 στήλες: 
        Είδος Κίνησης | Πλήκτρο | Διαγραφή
        """
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.row_widgets.clear()

        mappings = self.db.get_mappings(self.profile_id)

        if not mappings:
            ctk.CTkLabel(
                self.scroll_frame,
                text="⚠️ Δεν υπάρχουν καταχωρημένες κινήσεις για αυτό το προφίλ.",
                font=ctk.CTkFont(family="Segoe UI", size=14),
                text_color="#6c7281"
            ).pack(pady=40)
            return

        motion_names = {
            "mouth_open": "Στόμα Ανοιχτό 😮",
            "smile": "Χαμόγελο 😊",
            "left_eye_blink": "Αριστερό Βλέφαρο 👁️",
            "right_eye_blink": "Δεξί Βλέφαρο 👁️",
            "eyebrows_up": "Φρύδια Πάνω 😲",
            "eyebrows_frown": "Συνοφρύωση 😠",
            "jaw_left": "Σαγόνι Αριστερά 👈",
            "jaw_right": "Σαγόνι Δεξιά 👉",
            "lips_pucker": "Χείλη Μπροστά (O) 😗",
            "head_up": "Κεφάλι Πάνω ⬆️",
            "head_down": "Κεφάλι Κάτω ⬇️",
            "head_left": "Κεφάλι Αριστερά ⬅️",
            "head_right": "Κεφάλι Δεξιά ➡️",
            "head_roll": "Κλίση Κεφαλιού 🔄"
        }

        # Header 3 Στηλών
        header_frame = ctk.CTkFrame(self.scroll_frame, fg_color="#1f2128", height=35, corner_radius=6)
        header_frame.pack(fill="x", pady=(0, 8), padx=5)

        header_frame.grid_columnconfigure(0, weight=3)  # Είδος Κίνησης
        header_frame.grid_columnconfigure(1, weight=2)  # Πλήκτρο
        header_frame.grid_columnconfigure(2, weight=1)  # Ενέργεια

        ctk.CTkLabel(header_frame, text="Είδος Κίνησης", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a0a5b5").grid(row=0, column=0, sticky="w", padx=12, pady=5)
        ctk.CTkLabel(header_frame, text="Πλήκτρο", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a0a5b5").grid(row=0, column=1, sticky="w", padx=8, pady=5)
        ctk.CTkLabel(header_frame, text="Ενέργεια", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a0a5b5").grid(row=0, column=3, padx=8, pady=5)

        # Εγγραφές
        for item in mappings:
            m_id = item[0] if isinstance(item, (tuple, list)) else item.get('id')
            motion = item[1] if isinstance(item, (tuple, list)) else item.get('action')
            key = item[2] if isinstance(item, (tuple, list)) else item.get('mapped_key')

            row = ctk.CTkFrame(self.scroll_frame, fg_color="#181a20", corner_radius=8)
            row.pack(fill="x", pady=3, padx=5)

            row.grid_columnconfigure(0, weight=3)
            row.grid_columnconfigure(1, weight=2)
            row.grid_columnconfigure(2, weight=1)

            # 1. Είδος Κίνησης
            ctk.CTkLabel(
                row, text=motion_names.get(motion, motion),
                font=ctk.CTkFont(size=13, weight="bold"), text_color="#ffffff"
            ).grid(row=0, column=0, sticky="w", padx=12, pady=6)

            # 2. Πλήκτρο
            key_badge = ctk.CTkButton(
                row, text=str(key).upper(),
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#00f0ff", text_color="#111215",
                hover=False, width=70, height=24, corner_radius=5
            )
            key_badge.grid(row=0, column=1, sticky="w", padx=8, pady=6)

            # 3. Διαγραφή
            del_btn = ctk.CTkButton(
                row, text="🗑️ Διαγραφή",
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#ff4757", hover_color="#ff6b81", text_color="#ffffff",
                width=80, height=26, corner_radius=5,
                command=lambda mid=m_id: self.delete_entry(mid)
            )
            del_btn.grid(row=0, column=2, padx=8, pady=6)

    def enable_edit(self, mapping_id):
        if self.is_locked:
            return
            
        widgets = self.row_widgets[mapping_id]
        widgets["key_dropdown"].configure(state="normal")
        widgets["thresh_entry"].configure(state="normal")
        widgets["btn_edit"].configure(text="Ενεργό", fg_color="gray", state="disabled")

    def delete_entry(self, mapping_id):
        if self.is_locked:
            return

        self.db.delete_mapping(mapping_id)
        print(f"Διαγράφηκε η κίνηση με ID {mapping_id}")
        self.load_data()
        self.parent.refresh_active_mappings()

    def save_and_lock(self):
        if self.is_locked:
            self.is_locked = False
            self.btn_lock.configure(text="Αποθήκευση & Κλείδωμα", fg_color="#27ae60", hover_color="#2ecc71")
            for w in self.row_widgets.values():
                w["btn_edit"].configure(state="normal", text="Επεξεργασία", fg_color="#f39c12")
                w["btn_delete"].configure(state="normal")
            return

        for m_id, widgets in self.row_widgets.items():
            new_key = widgets["key_dropdown"].get()
            try:
                new_thresh = float(widgets["thresh_entry"].get())
            except ValueError:
                new_thresh = 0.05

            self.db.update_mapping(m_id, new_key, new_thresh)
            
            widgets["key_dropdown"].configure(state="disabled")
            widgets["thresh_entry"].configure(state="disabled")
            widgets["btn_edit"].configure(state="disabled")
            widgets["btn_delete"].configure(state="disabled")

        self.is_locked = True
        self.btn_lock.configure(text="🔒 ΚΛΕΙΔΩΜΕΝΟ (Πατήστε για ξεκλείδωμα)", fg_color="#c0392b", hover_color="#e74c3c")
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
        self.grab_set()

        self.font_title = ctk.CTkFont(family="Segoe UI", size=18, weight="bold")
        self.font_labels = ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        self.font_keys = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")

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
            ("Στόμα Ανοιχτό", "mouth_open"),
            ("Χαμόγελο", "smile"),
            ("Αριστερό Βλέφαρο", "left_eye_blink"),
            ("Δεξί Βλέφαρο", "right_eye_blink"),
            ("Φρύδια Πάνω", "eyebrows_up"),
            ("Συνοφρύωση", "eyebrows_frown"),
            ("Σαγόνι Αριστερά", "jaw_left"),
            ("Σαγόνι Δεξιά", "jaw_right"),
            ("Χείλη Μπροστά (O)", "lips_pucker"),
            ("Κεφάλι Πάνω", "head_up"),
            ("Κεφάλι Κάτω", "head_down"),
            ("Κεφάλι Αριστερά", "head_left"),
            ("Κεφάλι Δεξιά", "head_right"),
            ("Κλίση Κεφαλιού", "head_roll")
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

        keyboard_layout = [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
            ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
            ["A", "S", "D", "F", "G", "H", "J", "K", "L", "enter"],
            ["Z", "X", "C", "V", "B", "N", "M", "space", "up", "down"],
            ["left", "right", "left_click", "right_click"]
        ]

        for row_idx, row_keys in enumerate(keyboard_layout):
            row_frame = ctk.CTkFrame(keyboard_grid, fg_color="transparent")
            row_frame.pack(fill="x", pady=4)
            
            for key in row_keys:
                btn_width = 80 if key in ["space", "enter", "left_click", "right_click"] else 46
                display_text = key.upper()
                if key == "left_click": display_text = "L. CLICK"
                if key == "right_click": display_text = "R. CLICK"

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
            if isinstance(self.profile_id, str):
                digits = [s for s in self.profile_id.split() if s.isdigit()]
                clean_id = int(digits[0]) if digits else 1
            else:
                clean_id = int(self.profile_id)

            self.db.save_mapping(
                profile_id=clean_id,
                action=self.selected_motion,
                mapped_key=self.selected_key
            )
            print(f"✅ Επιτυχής καταχώρηση στη βάση (Προφίλ: {clean_id})!")

        except Exception as e:
            print(f"❌ Σφάλμα κατά την εγγραφή στη βάση δεδομένων: {e}")

        if hasattr(self.parent, 'load_profile_data'):
            self.parent.load_profile_data(self.profile_id)
        elif hasattr(self.parent, 'update_mappings_display'):
            self.parent.update_mappings_display()
        elif hasattr(self.parent, 'refresh_ui'):
            self.parent.refresh_ui()

        self.on_close()

    def on_close(self):
        self.grab_release()
        self.destroy()

class SmartControllerApp(ctk.CTk):
    def refresh_active_mappings(self):
        mappings = self.db.get_mappings(self.current_profile_id)
        self.active_mappings.clear()
        
        for m_id, action, key, threshold in mappings:
            self.active_mappings[action] = {"key": key, "threshold": threshold}
            
        print(f"Ενεργά Mappings ανανεώθηκαν: {self.active_mappings}")

    def __init__(self):
        self.active_mappings = {}
        self.pressed_keys = set()
        self.is_recording_motion = False
        self.recorded_landmarks = []
        self.recorded_frames = []
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

        # --- Παράμετροι Ποντικιού ---
        self.screen_w, self.screen_h = pydirectinput.size()
        self.mouse_control_active = True 
        
        self.mouse_pause_until = 0.0      
        self.last_injected_pos = None     

        self.smooth_x, self.smooth_y = self.screen_w // 2, self.screen_h // 2
        
        self.dwell_start_time = time.time()
        self.last_cursor_x, self.last_cursor_y = 0, 0
        self.dwell_threshold = 30  
        self.dwell_duration = 2.0  
        self.is_dwelling = False

        self._build_ui()
        self.load_profile_data(1)

        self.is_eyebrow_clicked = False
        
        # --- OpenCV Setup ---
        print("🔍 Προσπάθεια ανοίγματος της κάμερας στο ID: 0...")
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        print("✅ Η κάμερα στο ID 0 άνοιξε επιτυχώς!")
        
        self.neutral_nose_x = None  
        self.neutral_nose_y = None
        self.deadzone_radius = 0.025 
        
        self.cap.set(3, 640) 
        self.cap.set(4, 480)
        self.update_video()

    def _build_ui(self):
        """Κατασκευάζει το User Interface σε Μοντέρνο Stealth Στυλ."""
        ctk.set_appearance_mode("Dark")
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        font_main = ctk.CTkFont(family="Segoe UI", size=16, weight="bold")
        font_logo = ctk.CTkFont(family="Segoe UI", size=20, weight="bold")

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
        self.profile_selector.set("1")
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
        self.sens_value_label.pack(pady=(0, 20))

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

    def open_autonomous_selector(self):
        """Ανοίγει το παράθυρο πλέγματος των 6 παιχνιδιών."""
        AutonomousGameSelectorWindow(self)

    def change_profile(self, value):
        self.current_profile_id = int(value)
        print(f"--- Αλλαγή σε Προφίλ {self.current_profile_id} ---")
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

    def update_video(self):
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb_frame)

            if results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    if getattr(self, 'is_recording_motion', False):
                        self.recorded_landmarks.append(face_landmarks)
                        self.recorded_frames.append(rgb_frame.copy())

                    self.mp_drawing.draw_landmarks(
                        image=rgb_frame,
                        landmark_list=face_landmarks,
                        connections=self.mp_face_mesh.FACEMESH_TESSELATION,
                        landmark_drawing_spec=None,
                        connection_drawing_spec=self.mp_drawing_styles.get_default_face_mesh_tesselation_style()
                    )

                    if getattr(self, 'mouse_control_active', False):
                        current_time = time.time()
                        sensitivity = self.sens_slider.get()

                        nose = face_landmarks.landmark[1]

                        if getattr(self, 'neutral_nose_x', None) is None:
                            self.neutral_nose_x = nose.x
                            self.neutral_nose_y = nose.y
                            init_x, init_y = pyautogui.position()
                            self.virtual_x = float(init_x)
                            self.virtual_y = float(init_y)

                        actual_mouse_x, actual_mouse_y = pyautogui.position()
                        last_pos = getattr(self, 'last_injected_pos', None)
                        pause_until = getattr(self, 'mouse_pause_until', 0.0)

                        if last_pos is not None:
                            dist_moved = math.hypot(actual_mouse_x - last_pos[0], actual_mouse_y - last_pos[1])
                            if dist_moved > 25:
                                self.mouse_pause_until = current_time + 3.0
                                pause_until = self.mouse_pause_until
                                self.virtual_x = float(actual_mouse_x)
                                self.virtual_y = float(actual_mouse_y)

                        if current_time >= pause_until:
                            dx = nose.x - self.neutral_nose_x
                            dy = (nose.y - self.neutral_nose_y) * 1.6

                            displacement_length = math.hypot(dx, dy)
                            deadzone = 0.040

                            if displacement_length > deadzone:
                                excess = displacement_length - deadzone
                                speed = (excess ** 1.5) * 650 * sensitivity
                                move_x = (dx / displacement_length) * speed
                                move_y = (dy / displacement_length) * speed

                                self.virtual_x += move_x
                                self.virtual_y += move_y

                                self.virtual_x = max(0, min(self.screen_w - 1, self.virtual_x))
                                self.virtual_y = max(0, min(self.screen_h - 1, self.virtual_y))

                            target_x, target_y = self.apply_magnetic_snap(
                                int(self.virtual_x), int(self.virtual_y), snap_threshold=45
                            )

                            pydirectinput.moveTo(target_x, target_y)
                            self.last_injected_pos = (target_x, target_y)
                        else:
                            self.last_injected_pos = (actual_mouse_x, actual_mouse_y)
                            cv2.putText(rgb_frame, "PAUSED (MOUSE OVERRIDE)", (10, 30), 0, 0.8, (0, 0, 255), 2)

                        upper_lip = face_landmarks.landmark[13]
                        lower_lip = face_landmarks.landmark[14]

                        mouth_open_length = abs(lower_lip.y - upper_lip.y)
                        click_threshold = 0.06 / sensitivity

                        if mouth_open_length > click_threshold:
                            if not getattr(self, 'mouth_click_triggered', False):
                                pyautogui.click()
                                print("🎯 Click με το στόμα!")
                                self.mouth_click_triggered = True
                        else:
                            self.mouth_click_triggered = False

                    try:
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

                        active_mappings = getattr(self, 'active_mappings', {})
                        for action, data in active_mappings.items():
                            target_key = data["key"]
                            threshold = data["threshold"]

                            if action not in current_metrics:
                                continue

                            is_active = False

                            if action in ["mouth_open", "smile", "eyebrows_up", "cheek_puff"]:
                                is_active = current_metrics[action] > threshold
                            elif action in ["left_eye_blink", "right_eye_blink", "kiss", "jaw_left", "jaw_right", "nose_scrunch"]:
                                is_active = current_metrics[action] < threshold

                            pressed_keys = getattr(self, 'pressed_keys', set())
                            if is_active:
                                if target_key not in pressed_keys:
                                    pydirectinput.keyDown(target_key)
                                    pressed_keys.add(target_key)
                                    print(f"🟢 [ΕΝΕΡΓΟ] {action} -> Πατήθηκε: {target_key.upper()}")
                            else:
                                if target_key in pressed_keys:
                                    pydirectinput.keyUp(target_key)
                                    pressed_keys.remove(target_key)
                                    print(f"🔴 [ΑΝΕΝΕΡΓΟ] {action} -> Απελευθερώθηκε: {target_key.upper()}")

                    except Exception as e:
                        print(f"❌ ΣΦΑΛΜΑ ΣΤΑ GESTURES: {e}")

            img = Image.fromarray(rgb_frame)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(640, 480))
            self.video_label.configure(image=ctk_img)
            self.video_label.image = ctk_img

        self.after(33, self.update_video)

    def add_motion_event(self):
        db_instance = getattr(self, 'db', None)
        current_profile = self.profile_selector.get()
        MotionInputWindow(self, current_profile, db_instance)

    def open_review_window(self):
        review_popup = ProfileReviewWindow(self, self.current_profile_id, self.db)
        review_popup.grab_set()

    def on_closing(self):
        self.cap.release()
        self.destroy()

    def get_all_widgets(self, parent=None):
        if parent is None:
            parent = self
        widgets = []
        try:
            for child in parent.winfo_children():
                widgets.append(child)
                widgets.extend(self.get_all_widgets(child))
        except Exception:
            pass
        return widgets

    def apply_magnetic_snap(self, x, y, snap_threshold=50):
        try:
            closest_target = None
            min_dist_length = float('inf')

            for w in self.get_all_widgets():
                if isinstance(w, (ctk.CTkButton, ctk.CTkSlider, ctk.CTkSwitch, ctk.CTkCheckBox, ctk.CTkOptionMenu)):
                    if w.winfo_viewable():
                        wx = w.winfo_rootx()
                        wy = w.winfo_rooty()
                        ww = w.winfo_width()
                        wh = w.winfo_height()

                        center_x = wx + (ww / 2)
                        center_y = wy + (wh / 2)

                        dist_length = math.hypot(x - center_x, y - center_y)

                        if dist_length < snap_threshold and dist_length < min_dist_length:
                            min_dist_length = dist_length
                            closest_target = (int(center_x), int(center_y))

            if closest_target:
                return closest_target

        except Exception:
            pass

        return x, y

if __name__ == "__main__":
    app = SmartControllerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()