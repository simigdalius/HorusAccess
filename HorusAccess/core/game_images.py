"""Cover-art download for the installed-games selector.

The function is intentionally Tk-free so it can run in a worker thread; the
caller only has to hand the resulting ``PIL.Image`` back to the Tk thread.
"""

import io

import requests
from PIL import Image


def download_game_image(game_title, image_url=None, size=(180, 100)):
    """Κατεβάζει και κλιμακώνει την εικόνα του παιχνιδιού.

    Επιστρέφει ``PIL.Image`` ή ``None``. Δεν δημιουργεί κανένα Tk widget, ώστε να
    μπορεί να εκτελεστεί σε worker thread χωρίς να αγγίξει το Tk main thread.
    """
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) HorusAccess/1.0"}

    # 1. Δοκιμή λήψης από το απευθείας URL αν υπάρχει
    if image_url:
        try:
            res = requests.get(image_url, headers=headers, timeout=3)
            if res.status_code == 200:
                pil_img = Image.open(io.BytesIO(res.content)).convert("RGBA")
                return pil_img.resize(size, Image.Resampling.LANCZOS)
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
                    return pil_img.resize(size, Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"⚠️ Αποτυχία αυτόματης αναζήτησης εικόνας για {game_title}: {e}")

    return None
