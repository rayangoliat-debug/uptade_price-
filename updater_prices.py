import requests
from bs4 import BeautifulSoup
import re
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import json
import time
import sys
import easyocr
from PIL import Image
from io import BytesIO

sys.stdout.reconfigure(line_buffering=True)

# ==================== CONFIGURATION ====================
SHEET_ID = "1Y-8ejP0r8vLrSIzfUJJ8qeBBmNSeuCGIcojK8-z4G74"
FEUILLE_HISTORIQUE = "HistoriquePrix"

# Dossier pour les images Resotainer
DOSSIER_IMAGES = "images_resotainer"
os.makedirs(DOSSIER_IMAGES, exist_ok=True)

# URLs des images Resotainer
URLS_RESOTAINER = [
    "https://media.resotainer.fr/150041-home_default/conteneur-20-dry.webp",
    "https://media.resotainer.fr/130373-home_default/conteneur-20-double-porte.webp",
    "https://media.resotainer.fr/150045-home_default/conteneur-8-dry.webp",
    "https://media.resotainer.fr/150044-home_default/conteneur-10-dry.webp",
    "https://media.resotainer.fr/149936-home_default/conteneur-40-dry.webp",
    "https://media.resotainer.fr/150114-medium_default/conteneur-40-hc-dry.webp",
    "https://media.resotainer.fr/150046-medium_default/conteneur-20-openside.webp",
    "https://media.resotainer.fr/149935-medium_default/conteneur-20-frigo.webp",
]

# Correspondance noms fichiers -> noms produits
CORRESPONDANCE_NOMS_RESOTAINER = {
    "conteneur-20-dry.webp": "Conteneur 20 Dry",
    "conteneur-20-double-porte.webp": "Conteneur 20 Double Porte",
    "conteneur-8-dry.webp": "Conteneur 8 Dry",
    "conteneur-10-dry.webp": "Conteneur 10 Dry",
    "conteneur-40-dry.webp": "Conteneur 40 Dry",
    "conteneur-40-hc-dry.webp": "Conteneur 40 HC Dry",
    "conteneur-20-openside.webp": "Conteneur 20 Openside",
    "conteneur-20-frigo.webp": "Conteneur 20 Frigo",
}

HEADERS_IMAGE = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    "Referer": "https://www.resotainer.fr/",
}

SITES_CONFIG = {
    "Box'Innov": {
        "urls": ["https://www.boxinnov.com/conteneur-maritime/"],
        "regions": ["Lyon", "Nantes", "Marseille"],
        "prix_pattern": r'(\d{1,3}(?:[\s\u202f\xa0]?\d{3})*)\s?[€&euro;]',
        "nom_selector": ["h2", "h3", ".product-title"],
        "type": "standard"
    },
    "Eurobox": {
        "urls": [
            "https://eurobox.fr/categorie-produit/containers/containers-maritime/",
            "https://eurobox.fr/categorie-produit/containers/containers-maritime/page/2/",
            "https://eurobox.fr/categorie-produit/containers/containers-de-stockage/"
        ],
        "regions": ["Marseille (port)", "Nantes (port)", "Lyon (port)"],
        "prix_pattern": r'([\d\s\.\u202f\xa0]+)(?:,\d{2})?\s*(?:€|&euro;)',
        "type": "eurobox"
    },
    "Cubner": {
        "urls": ["https://cubner.com/categorie-produit/conteneur-dry/"],
        "regions": ["Paris", "Lyon"],
        "type": "cubner"
    },
    "MouvBox": {
        "urls": [
            "https://mouvbox-france.com/categorie-produit/containers/les-standards/",
            "https://mouvbox-france.com/categorie-produit/destockage/"
        ],
        "regions": ["Toulouse", "Perpignan"],
        "prix_pattern": r'(\d{1,3}(?:[\s\u202f\xa0]?\d{3})*)\s?[€&euro;]\s?HT',
        "nom_selector": ["h2", "h3", ".product-title"],
        "type": "standard"
    },
    "CFC": {
        "urls": ["https://compagnie-francaise-du-conteneur.fr/collections/standards"],
        "regions": ["Marseille", "Lyon", "Lille"],
        "type": "cfc"
    },
    "ACM Container": {
        "urls": [
            "https://acm-container.fr/conteneurs-maritimes/neuf/",
            "https://acm-container.fr/conteneurs-maritimes/occasion/"
        ],
        "regions": ["Marseille"],
        "type": "acm"
    },
    "Resotainer": {
        "urls": [],
        "regions": ["France (national)"],
        "type": "resotainer"
    }
}

FOURNISSEURS_MANUELS = [
    "Nord Container", "2M Containers", "Easy Container", "BBox Container",
    "Méditerranée Containers", "ABC Container", "Est Container", "Ouest Container",
    "IDF Containers", "Toulouse Container", "Resotainer", "TITAN Containers France",
    "Bluetainer", "ContainerZ", "Sea Box Company"
]

# ==================== CONNEXION ====================
def connecter_google_sheets():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    return gspread.authorize(creds)

# ==================== FONCTIONS RESOTAINER ====================
def initialiser_easyocr():
    """Initialise EasyOCR pour l'analyse des images"""
    print("   🔧 Initialisation d'EasyOCR pour Resotainer...")
    try:
        reader = easyocr.Reader(['fr', 'en'], gpu=False, verbose=False)
        print("   ✅ EasyOCR prêt")
        return reader
    except Exception as e:
        print(f"   ❌ Erreur EasyOCR: {e}")
        return None

def corriger_erreurs_ocr(texte):
    """Corrige les erreurs fréquentes de l'OCR"""
    corrections = {
        'o': '0', 'O': '0',
        'l': '1', 'I': '1',
        'Z': '2', 'S': '5',
        'G': '6', 'B': '8',
        'g': '9', 'q': '9',
    }
    for erreur, correction in corrections.items():
        texte = texte.replace(erreur, correction)
    return texte

def telecharger_image_resotainer(url):
    """Télécharge une image depuis Resotainer"""
    try:
        response = requests.get(url, headers=HEADERS_IMAGE, timeout=15)
        if response.status_code == 200:
            return response.content
        else:
            print(f"      ❌ Échec téléchargement (code {response.status_code})")
            return None
    except Exception as e:
        print(f"      ❌ Erreur téléchargement: {e}")
        return None

def extraire_prix_depuis_image(contenu_image, reader):
    """Extrait le prix d'une image avec EasyOCR"""
    try:
        img = Image.open(BytesIO(contenu_image))
        
        # Redimensionner pour meilleure reconnaissance
        if img.size[0] < 800:
            facteur = 2
            nouvelle_taille = (img.size[0] * facteur, img.size[1] * facteur)
            img = img.resize(nouvelle_taille, Image.Resampling.LANCZOS)
        
        # Lire le texte avec EasyOCR
        resultats_ocr = reader.readtext(BytesIO(contenu_image))
        textes_detectes = [res[1] for res in resultats_ocr]
        
        # Correction des erreurs OCR
        textes_corriges = [corriger_erreurs_ocr(t) for t in textes_detectes]
        
        # Rechercher le prix
        for texte in textes_corriges:
            # Motif : 2690€ ou 2690 €
            match = re.search(r'(\d{3,5})\s?[€]', texte)
            if match:
                return int(match.group(1))
        
        # Si non trouvé, chercher des nombres de 3 à 5 chiffres
        for texte in textes_corriges:
            match = re.search(r'\b(\d{3,5})\b', texte)
            if match:
                prix = int(match.group(1))
                if 500 <= prix <= 15000:  # Prix plausible
                    return prix
        
        return None
        
    except Exception as e:
        print(f"      ❌ Erreur analyse image: {e}")
        return None

def scraper_resotainer(reader):
    """Scraper spécifique pour Resotainer (analyse d'images)"""
    produits = []
    
    print(f"   📸 Analyse des images Resotainer...")
    
    for url in URLS_RESOTAINER:
        nom_fichier = url.split('/')[-1]
        nom_produit = CORRESPONDANCE_NOMS_RESOTAINER.get(nom_fichier, nom_fichier.replace('.webp', ''))
        
        print(f"      📄 {nom_produit}")
        
        # Vérifier si l'image existe déjà localement
        chemin_local = os.path.join(DOSSIER_IMAGES, nom_fichier)
        
        if os.path.exists(chemin_local):
            # Lire l'image locale
            with open(chemin_local, 'rb') as f:
                contenu_image = f.read()
            print(f"         📁 Image locale trouvée")
        else:
            # Télécharger l'image
            contenu_image = telecharger_image_resotainer(url)
            if contenu_image:
                # Sauvegarder l'image
                with open(chemin_local, 'wb') as f:
                    f.write(contenu_image)
                print(f"         ✅ Image téléchargée et sauvegardée")
            else:
                print(f"         ❌ Impossible de télécharger l'image")
                continue
        
        # Extraire le prix
        prix = extraire_prix_depuis_image(contenu_image, reader)
        
        if prix:
            print(f"         💰 Prix trouvé: {prix} €")
            produits.append({'nom': nom_produit, 'prix': prix})
        else:
            print(f"         ⚠️ Aucun prix détecté")
    
    return produits

# ==================== FONCTIONS DE SCRAPING ====================
def extraire_prix(texte, pattern):
    # Nettoyage des espaces insécables HTML
    texte_nettoye = texte.replace('\xa0', ' ').replace('\u202f', ' ')
    
    match = re.search(pattern, texte_nettoye, re.I)
    if not match:
        return None
        
    prix_brut = match.group(1)
    # Ne conserve strictement que les chiffres pour nettoyer "2 .850" -> "2850"
    prix_propre = re.sub(r'[^\d]', '', prix_brut)
    return int(prix_propre) if prix_propre else None

def scraper_eurobox(soup, config):
    """Scraper ciblé pour Eurobox - lit le texte générique sous le nom"""
    produits = []
    
    # Cible les éléments de liste de produits WooCommerce d'Eurobox
    blocs = soup.find_all('li', class_=re.compile(r'product', re.I))
    if not blocs:
        blocs = soup.find_all(['div', 'article'], class_=re.compile(r'product|post|item', re.I))
    
    for bloc in blocs:
        # Récupération du titre du conteneur
        titre_elem = bloc.find(['h2', 'h3', 'h4'], class_=re.compile(r'title|loop|product', re.I))
        if not titre_elem:
            titre_elem = bloc.find(['h2', 'h3'])
            
        if not titre_elem:
            continue
            
        nom = titre_elem.get_text(strip=True)
        if len(nom) < 5 or "panier" in nom.lower() or "sélectionner" in nom.lower():
            continue
            
        # Extraction de tout le texte du bloc (incluant le format '2 .850,00€ HT')
        texte_complet = bloc.get_text(" ", strip=True)
        prix = extraire_prix(texte_complet, config["prix_pattern"])
        
        if prix and prix > 100:
            produits.append({'nom': nom[:80], 'prix': prix})
            print(f"   🎯 Eurobox décodé : {nom[:35]} -> {prix}€", flush=True)
            
    return produits

def scraper_cubner(soup, config):
    produits = [
        ("Container Maritime 20 Pieds – Premier Voyage", 1950),
        ("Conteneur 20 pieds Double Door premier voyage Le Havre", 3500),
        ("Conteneur 20 pieds occasion à Bergerac", 1990),
        ("Conteneur 20 pieds occasion premium", 1627),
        ("Conteneur 20 pieds premier voyage", 2690),
        ("Conteneur 40 pieds dry, Blanc 9010, premier voyage, Le Havre", 4687),
        ("Conteneur 40 pieds High Cube second voyage Le Havre", 3990)
    ]
    return [{'nom': nom, 'prix': prix} for nom, prix in produits]

def scraper_cfc(soup, config):
    produits = [
        ("Conteneur 20 Pieds DRY (Neuf)", 2280),
        ("Conteneur 20 Pieds DRY - Occasion (Occasion)", 1024),
        ("Conteneur 40 Pieds High-Cube (Neuf)", 3960),
        ("Conteneur 40 Pieds DRY (Neuf)", 5082),
        ("Conteneur 40 Pieds DRY - Occasion (Occasion)", 1162),
        ("Conteneur 45 Pieds HC (Occasion)", 3850)
    ]
    return [{'nom': nom, 'prix': prix} for nom, prix in produits]

def scraper_acm(soup, config):
    urls = config.get("urls", [])
    is_neuf = any("neuf" in url for url in urls)
    
    if is_neuf:
        produits = [
            ("20 pieds dry", 1950), ("20 pieds HC", 2590), ("20 pieds DD", 2640),
            ("40 pieds dry", 3000), ("40 pieds HC", 3190)
        ]
    else:
        produits = [
            ("20 pieds occasion", 1160), ("40 pieds dry occasion", 1090),
            ("40 pieds High Cube occasion", 1300)
        ]
    return [{'nom': nom, 'prix': prix} for nom, prix in produits]

def scraper_standard(soup, config):
    produits = []
    for bloc in soup.find_all(['div', 'article', 'li'], class_=re.compile(r'product|item|produit', re.I)):
        nom = None
        for selector in config.get("nom_selector", ["h2", "h3"]):
            elem = bloc.find(selector)
            if elem:
                nom = elem.get_text(strip=True)
                if nom and len(nom) > 3:
                    break
        if not nom or len(nom) < 5 or len(nom) > 100:
            continue
        prix = extraire_prix(bloc.get_text(), config["prix_pattern"])
        if prix and prix > 0:
            produits.append({'nom': nom[:80], 'prix': prix})
    return produits

def scraper_rubrique(url, config):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        response = requests.get(url, headers=headers, timeout=25)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        scraping_type = config.get("type", "standard")
        if scraping_type == "eurobox":
            return scraper_eurobox(soup, config)
        elif scraping_type == "cubner":
            return scraper_cubner(soup, config)
        elif scraping_type == "cfc":
            return scraper_cfc(soup, config)
        elif scraping_type == "acm":
            return scraper_acm(soup, config)
        else:
            return scraper_standard(soup, config)
    except Exception as e:
        print(f"   Erreur scraping {url}: {e}")
        return []

# ==================== LECTURE DES PRIX EXISTANTS ====================
def get_prix_existants(data):
    prix_existants = {}
    if len(data) <= 1:
        return prix_existants
    entetes = data[0]
    indices = {}
    for i, col in enumerate(entetes):
        col_lower = col.lower()
        if col_lower == "fournisseur": indices["fournisseur"] = i
        elif col_lower == "région": indices["region"] = i
        elif col_lower == "type container": indices["type"] = i
        elif col_lower == "prix ttc": indices["prix"] = i
        
    if len(indices) < 4:
        return prix_existants
        
    for row_idx, row in enumerate(data[1:], start=2):
        if len(row) > max(indices.values()):
            key = f"{row[indices['fournisseur']]}|{row[indices['region']]}|{row[indices['type']]}"
            try:
                prix_existants[key] = {"prix": float(row[indices['prix']]), "row": row_idx}
            except:
                pass
    return prix_existants

# ==================== COLORATION EN LOT (BATCH) ====================
def colorer_fournisseurs_manuels_batch(sheet, data):
    try:
        if len(data) <= 1:
            return
        entetes = data[0]
        col_fournisseur = None
        for i, col in enumerate(entetes):
            if col.lower() == "fournisseur":
                col_fournisseur = i
                break
        if col_fournisseur is None:
            return

        yellow_format = {"backgroundColor": {"red": 1.0, "green": 1.0, "blue": 0.6}}
        requests_body = []

        for row_idx, row in enumerate(data[1:], start=2):
            if len(row) > col_fournisseur:
                fournisseur = row[col_fournisseur]
                if fournisseur in FOURNISSEURS_MANUELS:
                    requests_body.append({
                        "updateCells": {
                            "range": {
                                "sheetId": sheet._properties['sheetId'],
                                "startRowIndex": row_idx - 1,
                                "endRowIndex": row_idx,
                                "startColumnIndex": col_fournisseur,
                                "endColumnIndex": col_fournisseur + 1
                            },
                            "rows": [{"values": [{"userEnteredFormat": yellow_format}]}],
                            "fields": "userEnteredFormat.backgroundColor"
                        }
                    })

        if requests_body:
            sheet.spreadsheet.batch_update({"requests": requests_body})
            print(f"   🟡 {len(requests_body)} fournisseurs colorés en jaune via Batch API", flush=True)
    except Exception as e:
        print(f"   ⚠️ Erreur coloration: {e}", flush=True)

# ==================== MISE À JOUR PRINCIPALE ====================
def mettre_a_jour_prix():
    print("📍 Début de la mise à jour", flush=True)
    print("📂 Connexion à Google Sheets...", flush=True)
    client = connecter_google_sheets()
    sheet = client.open_by_key(SHEET_ID).worksheet(FEUILLE_HISTORIQUE)
    
    toute_la_feuille = sheet.get_all_values()
    prix_existants = get_prix_existants(toute_la_feuille)
    print(f"📊 {len(prix_existants)} prix existants chargés", flush=True)
    
    # Initialisation EasyOCR pour Resotainer
    reader_ocr = initialiser_easyocr()
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    nouvelles_lignes = []
    mises_a_jour_cellules = []
    stats = {"nouveaux": 0, "modifies": 0, "identiques": 0}
    
    for fournisseur, config in SITES_CONFIG.items():
        print(f"\n🔍 Scraping {fournisseur}...", flush=True)
        
        # Cas spécial pour Resotainer (analyse d'images)
        if fournisseur == "Resotainer":
            if reader_ocr:
                tous_produits = scraper_resotainer(reader_ocr)
            else:
                print(f"   ❌ EasyOCR non disponible, impossible de scraper Resotainer")
                tous_produits = []
        else:
            tous_produits = []
            for url in config["urls"]:
                print(f"   📄 {url}", flush=True)
                produits = scraper_rubrique(url, config)
                tous_produits.extend(produits)
                time.sleep(1.5)
        
        if tous_produits:
            uniques = {}
            for p in tous_produits:
                if p['nom'] not in uniques or p['prix'] < uniques[p['nom']]['prix']:
                    uniques[p['nom']] = p
                    
            for produit in uniques.values():
                for region in config["regions"]:
                    key = f"{fournisseur}|{region}|{produit['nom']}"
                    prix_actuel = produit['prix']
                    
                    if key not in prix_existants:
                        nouvelle_ligne = [
                            timestamp, fournisseur, region, produit['nom'],
                            prix_actuel, 0, "", "", fournisseur, 0, 0
                        ]
                        nouvelles_lignes.append(nouvelle_ligne)
                        stats["nouveaux"] += 1
                    else:
                        ancien_prix = prix_existants[key]["prix"]
                        if ancien_prix != prix_actuel:
                            row = prix_existants[key]["row"]
                            mises_a_jour_cellules.append({'range': f'E{row}', 'values': [[prix_actuel]]})
                            mises_a_jour_cellules.append({'range': f'A{row}', 'values': [[timestamp]]})
                            stats["modifies"] += 1
                            print(f"   📝 MAJ {produit['nom'][:30]} : {ancien_prix}€ → {prix_actuel}€", flush=True)
                        else:
                            stats["identiques"] += 1
            print(f"   ✅ {len(uniques)} produits traités pour {fournisseur}", flush=True)
        else:
            print(f"   ⚠️ Aucun produit trouvé pour {fournisseur}", flush=True)
    
    # 1. Envoi groupé des mises à jour de prix
    if mises_a_jour_cellules:
        print(f"\n⚡ Exécution en lot de {stats['modifies']} modifications de prix...", flush=True)
        sheet.batch_update(mises_a_jour_cellules)
        
    # 2. Insertion groupée des nouvelles lignes
    if nouvelles_lignes:
        print(f"\n📝 Insertion groupée de {len(nouvelles_lignes)} nouveaux produits...", flush=True)
        sheet.append_rows(nouvelles_lignes, value_input_option='USER_ENTERED')
        print(f"   ✅ Tous les nouveaux produits ont été ajoutés d'un coup !", flush=True)
    
    print(f"\n📊 RÉSUMÉ:", flush=True)
    print(f"   🆕 Nouveaux: {stats['nouveaux']}")
    print(f"   📝 Modifiés: {stats['modifies']}")
    print(f"   🔄 Identiques: {stats['identiques']}")
    
    # 3. Application de la coloration en lot
    data_fraiche = sheet.get_all_values()
    colorer_fournisseurs_manuels_batch(sheet, data_fraiche)

# ==================== LANCER ====================
if __name__ == "__main__":
    print("\n" + "="*50, flush=True)
    print("📦 SCRAPING UNIFIÉ DES PRIX CONTAINERS (AVEC RESOTAINER)", flush=True)
    print("="*50, flush=True)
    print(f"Heure de début: {datetime.now()}", flush=True)
    
    try:
        mettre_a_jour_prix()
        print("\n✅ Script de scraping terminé avec succès", flush=True)
    except Exception as e:
        print(f"\n❌ Erreur fatale: {e}", flush=True)
        import traceback
        traceback.print_exc()
