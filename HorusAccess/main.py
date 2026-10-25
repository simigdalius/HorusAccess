from gui.main import SmartControllerApp

# Draw the face mesh over the camera preview. Set to False to hide the overlay
# (restart the app afterwards). Everything else keeps working either way.
SHOW_FACE_MESH = True

def run_app():
    print("Ξεκινάει το Smart Controller...")
    app = SmartControllerApp(show_face_mesh=SHOW_FACE_MESH)
    
    # Διασφαλίζουμε ότι η κάμερα κλείνει σωστά
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # Εκκίνηση του γραφικού περιβάλλοντος
    app.mainloop()

if __name__ == "__main__":
    run_app()
