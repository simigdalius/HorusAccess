from gui.gui_main import SmartControllerApp

def run_app():
    print("Ξεκινάει το Smart Controller...")
    app = SmartControllerApp()
    
    # Διασφαλίζουμε ότι η κάμερα κλείνει σωστά
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # Εκκίνηση του γραφικού περιβάλλοντος
    app.mainloop()

if __name__ == "__main__":
    run_app()