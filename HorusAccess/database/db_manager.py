import sqlite3
import os

class DBManager:
    def __init__(self, db_name="smart_controller.db"):
        # Βρίσκει τον φάκελο όπου βρίσκεται το τρέχον αρχείο (db_manager.py)
        # και αποθηκεύει εκεί τη βάση, ώστε να είναι πάντα στο σωστό μέρος.
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(current_dir, db_name)
        
        self._create_tables()
        self._initialize_profiles()

    def _get_connection(self):
        """Επιστρέφει μια νέα σύνδεση στη βάση."""
        return sqlite3.connect(self.db_path)

    def _create_tables(self):
        """Δημιουργεί τους πίνακες αν δεν υπάρχουν ήδη."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Πίνακας Προφίλ (Αυστηρά ID 1 έως 5)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY CHECK (id >= 1 AND id <= 5),
                    name TEXT NOT NULL,
                    sensitivity REAL DEFAULT 1.0
                )
            ''')
            
            # Πίνακας Αντιστοιχίσεων (Mappings)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER,
                    facial_action TEXT NOT NULL,
                    mapped_key TEXT NOT NULL,
                    FOREIGN KEY (profile_id) REFERENCES profiles(id),
                    UNIQUE(profile_id, facial_action)
                )
            ''')
            conn.commit()

    def _initialize_profiles(self):
        """Δημιουργεί τα 5 default profiles αν η βάση είναι άδεια."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM profiles")
            if cursor.fetchone()[0] == 0:
                profiles_data = [
                    (1, "Profile 1", 1.0),
                    (2, "Profile 2", 1.0),
                    (3, "Profile 3", 1.0),
                    (4, "Profile 4", 1.0),
                    (5, "Profile 5", 1.0)
                ]
                cursor.executemany('''
                    INSERT INTO profiles (id, name, sensitivity)
                    VALUES (?, ?, ?)
                ''', profiles_data)
                conn.commit()

    # --- ΜΕΘΟΔΟΙ ΓΙΑ ΤΑ ΠΡΟΦΙΛ ---

    def get_all_profiles(self):
        """Επιστρέφει όλα τα προφίλ και τις ρυθμίσεις τους."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, sensitivity FROM profiles ORDER BY id")
            return cursor.fetchall()

    def update_profile_settings(self, profile_id: int, name: str, sensitivity: float):
        """Ενημερώνει το όνομα και την ευαισθησία ενός συγκεκριμένου προφίλ."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE profiles 
                SET name = ?, sensitivity = ? 
                WHERE id = ?
            ''', (name, sensitivity, profile_id))
            conn.commit()

    # --- ΜΕΘΟΔΟΙ ΓΙΑ ΤΑ MAPPINGS ---

    def save_mapping(self, profile_id: int, facial_action: str, mapped_key: str):
        """
        Αποθηκεύει ή ενημερώνει μια αντιστοίχιση.
        π.χ. save_mapping(1, 'mouth_open', 'space')
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Το INSERT OR REPLACE δουλεύει χάρη στο UNIQUE(profile_id, facial_action)
            cursor.execute('''
                INSERT OR REPLACE INTO mappings (profile_id, facial_action, mapped_key)
                VALUES (?, ?, ?)
            ''', (profile_id, facial_action, mapped_key))
            conn.commit()

    def get_mappings(self, profile_id: int):
        """Επιστρέφει όλες τις αντιστοιχίσεις (ως dictionary) για ένα προφίλ."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT facial_action, mapped_key 
                FROM mappings 
                WHERE profile_id = ?
            ''', (profile_id,))
            
            # Μετατροπή των αποτελεσμάτων σε dictionary για εύκολη χρήση στον κώδικα
            return {row[0]: row[1] for row in cursor.fetchall()}

    def delete_mapping(self, profile_id: int, facial_action: str):
        """Διαγράφει μια συγκεκριμένη αντιστοίχιση."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM mappings 
                WHERE profile_id = ? AND facial_action = ?
            ''', (profile_id, facial_action))
            conn.commit()

    def clear_all_profile_mappings(self, profile_id: int):
        """Καθαρίζει όλες τις αντιστοιχίσεις ενός προφίλ (επαναφορά σε κενό)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM mappings WHERE profile_id = ?", (profile_id,))
            conn.commit()

# --- Παράδειγμα Χρήσης (Τρέχει μόνο αν εκτελέσεις απευθείας αυτό το αρχείο) ---
if __name__ == "__main__":
    db = DBManager()
    
    # 1. Έλεγχος προφίλ
    print("Αρχικά Προφίλ:")
    print(db.get_all_profiles())
    
    # 2. Ενημέρωση ρυθμίσεων προφίλ 1
    db.update_profile_settings(1, "Gaming Profile", 1.5)
    
    # 3. Προσθήκη Mappings
    db.save_mapping(1, "left_eye_blink", "a")
    db.save_mapping(1, "right_eye_blink", "d")
    db.save_mapping(1, "mouth_open", "space")
    
    # 4. Ανάγνωση Mappings
    print("\nMappings για το Profile 1:")
    print(db.get_mappings(1))
    
    # 5. Αλλαγή ενός mapping (επανεγγραφή)
    db.save_mapping(1, "mouth_open", "enter")
    print("\nΕνημερωμένα Mappings για το Profile 1:")
    print(db.get_mappings(1))