import sqlite3
import os

class DBManager:
    def __init__(self, db_name="smart_controller.db"):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(current_dir, db_name)
        
        self._create_tables()
        self._initialize_profiles()

    def _get_connection(self):
        """Επιστρέφει μια νέα σύνδεση στη βάση."""
        return sqlite3.connect(self.db_path)

    def _create_tables(self):
        """Δημιουργεί τους πίνακες με ενσωματωμένο το threshold."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Πίνακας Προφίλ
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY CHECK (id >= 1 AND id <= 5),
                    name TEXT NOT NULL,
                    sensitivity REAL DEFAULT 1.0
                )
            ''')
            
            # Πίνακας Αντιστοιχίσεων (Ενημερωμένος)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER,
                    action TEXT NOT NULL,
                    mapped_key TEXT NOT NULL,
                    threshold REAL DEFAULT 0.05,
                    FOREIGN KEY (profile_id) REFERENCES profiles(id),
                    UNIQUE(profile_id, action)
                )
            ''')
            conn.commit()

    def _initialize_profiles(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM profiles")
            if cursor.fetchone()[0] == 0:
                profiles_data = [(i, f"Profile {i}", 1.0) for i in range(1, 6)]
                cursor.executemany('''
                    INSERT INTO profiles (id, name, sensitivity)
                    VALUES (?, ?, ?)
                ''', profiles_data)
                conn.commit()

    # --- ΜΕΘΟΔΟΙ ΓΙΑ ΤΑ ΠΡΟΦΙΛ ---
    def get_all_profiles(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, sensitivity FROM profiles ORDER BY id")
            return cursor.fetchall()

    def update_profile_settings(self, profile_id: int, name: str, sensitivity: float):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE profiles SET name = ?, sensitivity = ? WHERE id = ?', 
                           (name, sensitivity, profile_id))
            conn.commit()

    # --- ΜΕΘΟΔΟΙ ΓΙΑ ΤΑ MAPPINGS ---
    def save_mapping(self, profile_id: int, action: str, mapped_key: str, threshold: float = 0.05):
        """Αποθηκεύει τη νέα κίνηση και το όριό της."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO mappings (profile_id, action, mapped_key, threshold)
                VALUES (?, ?, ?, ?)
            ''', (profile_id, action, mapped_key, threshold))
            conn.commit()

    def get_mappings(self, profile_id: int):
        """Επιστρέφει τις κινήσεις του προφίλ: (id, action, mapped_key, threshold)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, action, mapped_key, threshold 
                FROM mappings 
                WHERE profile_id = ?
            ''', (profile_id,))
            return cursor.fetchall()

    def update_mapping(self, mapping_id: int, new_key: str, new_threshold: float):
        """Ενημερώνει το πλήκτρο και την ευαισθησία (Από το Review Window)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE mappings 
                SET mapped_key = ?, threshold = ? 
                WHERE id = ?
            ''', (new_key, new_threshold, mapping_id))
            conn.commit()

    def delete_mapping(self, mapping_id: int):
        """Διαγράφει οριστικά την κίνηση βάσει του μοναδικού ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM mappings WHERE id = ?', (mapping_id,))
            conn.commit()