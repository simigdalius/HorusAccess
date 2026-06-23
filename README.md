# HorusAccess

Το **HorusAccess** είναι μια εφαρμογή υποστηρικτικής τεχνολογίας, σχεδιασμένη ως διπλωματική εργασία για την υποστήριξη ατόμων με κινητικές αναπηρίες. Επιτρέπει τον πλήρη χειρισμό του υπολογιστή μέσω κινήσεων του προσώπου και εκφράσεων, χρησιμοποιώντας υπολογιστική όραση.

## 🛠 Τεχνολογίες
- **UI:** [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)
- **Computer Vision:** [OpenCV](https://opencv.org/)
- **Face Tracking:** [MediaPipe Face Mesh](https://developers.google.com/mediapipe/solutions/vision/face_landmarker)
- **Input:** [PyDirectInput](https://github.com/learncodebygaming/pydirectinput)
- **Database:** SQLite

## 📂 Δομή Project
```text
HorusAccess/
├── main.py              # Entry point
├── gui/
│   └── gui_main.py      # GUI, MediaPipe integration & Event logic
├── database/
│   └── db_manager.py    # Διαχείριση βάσης δεδομένων SQLite
└── README.md

