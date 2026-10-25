import contextlib
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

    @contextlib.contextmanager
    def _connection(self):
        """Σύνδεση που κάνει commit/rollback και κλείνει πάντα στο τέλος."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _create_tables(self):
        """Δημιουργεί τους πίνακες με ενσωματωμένο το threshold."""
        with self._connection() as conn:
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

            # Πίνακας Ρυθμίσεων (key/value) - π.χ. το τελευταίο ενεργό προφίλ
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

    def _initialize_profiles(self):
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM profiles")
            if cursor.fetchone()[0] == 0:
                profiles_data = [(i, f"Profile {i}", 1.0) for i in range(1, 6)]
                cursor.executemany('''
                    INSERT INTO profiles (id, name, sensitivity)
                    VALUES (?, ?, ?)
                ''', profiles_data)

    # --- ΜΕΘΟΔΟΙ ΓΙΑ ΤΑ ΠΡΟΦΙΛ ---
    def get_all_profiles(self):
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, sensitivity FROM profiles ORDER BY id")
            return cursor.fetchall()

    def update_profile_settings(self, profile_id: int, name: str, sensitivity: float):
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE profiles SET name = ?, sensitivity = ? WHERE id = ?', 
                           (name, sensitivity, profile_id))

    def update_profile_sensitivity(self, profile_id: int, sensitivity: float):
        """Αποθηκεύει μόνο την ευαισθησία του προφίλ."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE profiles SET sensitivity = ? WHERE id = ?',
                (float(sensitivity), profile_id),
            )

    def update_profile_name(self, profile_id: int, name: str):
        """Αποθηκεύει το όνομα παιχνιδιού/εφαρμογής που αντιστοιχεί στο προφίλ."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE profiles SET name = ? WHERE id = ?',
                (str(name), profile_id),
            )

    def get_profile_name(self, profile_id: int):
        """Επιστρέφει το αποθηκευμένο όνομα ή ``None`` για προεπιλεγμένο προφίλ."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM profiles WHERE id = ?", (profile_id,))
            row = cursor.fetchone()

        if not row or not row[0]:
            return None

        name = row[0].strip()
        if not name or name == f"Profile {profile_id}":
            return None

        # Συμβατότητα με την παλιά μορφή "Προφίλ N (Game)".
        prefix = f"Προφίλ {profile_id} ("
        if name.startswith(prefix) and name.endswith(")"):
            return name[len(prefix):-1].strip() or None

        return name

    # --- ΜΕΘΟΔΟΙ ΓΙΑ ΤΑ MAPPINGS ---
    def save_mapping(self, profile_id: int, action: str, mapped_key: str,
                     threshold=None, default_threshold=0.05):
        """Αποθηκεύει τη νέα κίνηση και το όριό της.

        Το ``threshold=None`` διατηρεί την υπάρχουσα τιμή, ώστε μια αλλαγή
        πλήκτρου να μη μηδενίζει την ευαισθησία που είχε ορίσει ο χρήστης. Για
        νέα εγγραφή χρησιμοποιείται το ``default_threshold`` (ο καλών περνά το
        προεπιλεγμένο όριο της συγκεκριμένης κίνησης· το 0.05 μένει ως
        συμβατό fallback).
        """
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO mappings (profile_id, action, mapped_key, threshold)
                VALUES (?, ?, ?, COALESCE(?, ?))
                ON CONFLICT(profile_id, action) DO UPDATE SET
                    mapped_key = excluded.mapped_key,
                    threshold = COALESCE(?, mappings.threshold, ?)
            ''', (profile_id, action, mapped_key, threshold,
                  default_threshold, threshold, default_threshold))

    def get_mappings(self, profile_id: int):
        """Επιστρέφει τις κινήσεις του προφίλ: (id, action, mapped_key, threshold)."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, action, mapped_key, threshold 
                FROM mappings 
                WHERE profile_id = ?
            ''', (profile_id,))
            return cursor.fetchall()

    def update_mapping(self, mapping_id: int, new_key: str, new_threshold: float):
        """Ενημερώνει το πλήκτρο και την ευαισθησία (Από το Review Window)."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE mappings 
                SET mapped_key = ?, threshold = ? 
                WHERE id = ?
            ''', (new_key, new_threshold, mapping_id))

    def delete_mapping(self, mapping_id: int):
        """Διαγράφει οριστικά την κίνηση βάσει του μοναδικού ID."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM mappings WHERE id = ?', (mapping_id,))

    def migrate_legacy_thresholds(self, defaults, legacy_value=0.05,
                                  setting_key="threshold_defaults_v2"):
        """Αντικαθιστά μία φορά το παλιό ενιαίο όριο με τα όρια ανά κίνηση.

        Αλλάζονται μόνο οι εγγραφές που έχουν ακριβώς την παλιά προεπιλογή
        (``legacy_value``), άρα οι τιμές που έχει πειράξει ο χρήστης μένουν
        ανέπαφες. Επιστρέφει το πλήθος των εγγραφών που ενημερώθηκαν.
        """
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (setting_key,))
            row = cursor.fetchone()
            if row and str(row[0]) == "1":
                return 0

            cursor.execute(
                "SELECT id, action FROM mappings WHERE ABS(threshold - ?) < 1e-9",
                (float(legacy_value),),
            )
            updates = []
            for mapping_id, action in cursor.fetchall():
                new_threshold = defaults.get(action)
                if new_threshold is None:
                    continue
                updates.append((float(new_threshold), mapping_id))

            if updates:
                cursor.executemany(
                    "UPDATE mappings SET threshold = ? WHERE id = ?",
                    updates,
                )

            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (setting_key, "1"),
            )
            return len(updates)

    # --- ΜΕΘΟΔΟΙ ΓΙΑ ΤΙΣ ΡΥΘΜΙΣΕΙΣ ---
    def get_setting(self, key: str, default=None):
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value):
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )

    def get_last_profile(self) -> int:
        """Επιστρέφει το τελευταίο ενεργό προφίλ (default 1)."""
        try:
            profile_id = int(self.get_setting("last_profile", 1))
        except (TypeError, ValueError):
            return 1
        return profile_id if 1 <= profile_id <= 5 else 1

    def set_last_profile(self, profile_id: int):
        self.set_setting("last_profile", int(profile_id))
