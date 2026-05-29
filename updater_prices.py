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

sys.stdout.reconfigure(line_buffering=True)

# ==================== CONFIGURATION ====================
SHEET_ID = "1Y-8ejP0r8vLrSIzfUJJ8qeBBmNSeuCGIcojK8-z4G74"
FEUILLE_HISTORIQUE = "HistoriquePrix"

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
        "prix_pattern": r'(\d{1,3}(?:[\s\u202f\xa0]?\d{3})*)\s?[€&euro;]\s?HT',
        "nom_selector": ["h2", "h3", ".product-title"],
        "type": "standard"
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

# ==================== GESTION DES ERREURS ====================
def ajouter_avec_retry(sheet, ligne, max_retries=3):
    for i in range(max_retries):
        try:
            sheet.append_row(ligne, value_input_option='USER_ENTERED')
            return True
        except Exception as e:
            if "429" in str(e) and i < max_retries - 1:
                wait = (i + 1) * 5
                print(f"   ⏳ Quota dépassé, pause de {wait}s...", flush=True)
                time.sleep(wait)
            else:
                print(f"   ❌ Erreur: {e}", flush=True)
                return False
    return False

# ==================== FONCTIONS DE SCRAPING ====================
def extraire_prix(texte, pattern):
    match = re.search(pattern, texte, re.I)
    if not match:
        return None
    prix_brut = match.group(1)
    prix_propre = re.sub(r'[^\d]', '', prix_brut)
    return int(prix_propre) if prix_propre else None

def scraper_cubner(soup, config):
    """Scraping spécifique pour Cubner (liste fixe)"""
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
    """Scraping spécifique pour CFC (liste fixe)"""
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
    """Scraping spécifique pour ACM Container (liste fixe)"""
    urls = config.get("urls", [])
    is_neuf = any("neuf" in url for url in urls)
    
    if is_neuf:
        produits = [
            ("20 pieds dry", 1950),
            ("20 pieds HC", 2590),
            ("20 pieds DD", 2640),
            ("40 pieds dry", 3000),
            ("40 pieds HC", 3190)
        ]
    else:
        produits = [
            ("20 pieds occasion", 1160),
            ("40 pieds dry occasion", 1090),
            ("40 pieds High Cube occasion", 1300)
        ]
    return [{'nom': nom, 'prix': prix} for nom, prix in produits]

def scraper_standard(soup, config):
    """Scraping standard pour les autres sites"""
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
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        scraping_type = config.get("type", "standard")
        if scraping_type == "cubner":
            produits = scraper_cubner(soup, config)
        elif scraping_type == "cfc":
            produits = scraper_cfc(soup, config)
        elif scraping_type == "acm":
            produits = scraper_acm(soup, config)
        else:
            produits = scraper_standard(soup, config)
        return produits
    except Exception as e:
        print(f"   Erreur scraping {url}: {e}")
        return []

# ==================== LECTURE DES PRIX EXISTANTS ====================
def get_prix_existants(sheet):
    prix_existants = {}
    try:
        data = sheet.get_all_values()
        if len(data) <= 1:
            return prix_existants
        entetes = data[0]
        indices = {}
        for i, col in enumerate(entetes):
            col_lower = col.lower()
            if col_lower == "fournisseur":
                indices["fournisseur"] = i
            elif col_lower == "région":
                indices["region"] = i
            elif col_lower == "type container":
                indices["type"] = i
            elif col_lower == "prix ttc":
                indices["prix"] = i
        if len(indices) < 4:
            return prix_existants
        for row_idx, row in enumerate(data[1:], start=2):
            if len(row) > max(indices.values()):
                key = f"{row[indices['fournisseur']]}|{row[indices['region']]}|{row[indices['type']]}"
                try:
                    prix_existants[key] = {"prix": float(row[indices['prix']]), "row": row_idx}
                except:
                    pass
    except Exception as e:
        print(f"   ⚠️ Erreur lecture existants: {e}")
    return prix_existants

def mettre_a_jour_prix_existant(sheet, row, nouveau_prix, timestamp):
    try:
        sheet.update_cell(row, 5, nouveau_prix)
        sheet.update_cell(row, 1, timestamp)
        return True
    except Exception as e:
        print(f"   ⚠️ Erreur mise à jour ligne {row}: {e}")
        return False

# ==================== COLORATION ====================
def colorer_fournisseurs_manuels(sheet):
    try:
        data = sheet.get_all_values()
        if len(data) <= 1:
            return
        entetes = data[0]
        col_fournisseur = None
        for i, col in enumerate(entetes):
            if col.lower() == "fournisseur":
                col_fournisseur = i + 1
                break
        if not col_fournisseur:
            return
        yellow_format = {"backgroundColor": {"red": 1.0, "green": 1.0, "blue": 0.6}}
        count = 0
        for row in range(2, len(data) + 1):
            fournisseur = sheet.cell(row, col_fournisseur).value
            if fournisseur in FOURNISSEURS_MANUELS:
                sheet.format(f"{chr(64 + col_fournisseur)}{row}", yellow_format)
                count += 1
        print(f"   🟡 {count} fournisseurs colorés en jaune", flush=True)
    except Exception as e:
        print(f"   ⚠️ Erreur coloration: {e}", flush=True)

# ==================== MISE À JOUR PRINCIPALE ====================
def mettre_a_jour_prix():
    print("📍 Début de la mise à jour", flush=True)
    print("📂 Connexion à Google Sheets...", flush=True)
    client = connecter_google_sheets()
    sheet = client.open_by_key(SHEET_ID).worksheet(FEUILLE_HISTORIQUE)
    
    prix_existants = get_prix_existants(sheet)
    print(f"📊 {len(prix_existants)} prix existants chargés", flush=True)
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    nouvelles_lignes = []
    stats = {"nouveaux": 0, "modifies": 0, "identiques": 0}
    
    for fournisseur, config in SITES_CONFIG.items():
        print(f"\n🔍 Scraping {fournisseur}...", flush=True)
        tous_produits = []
        for url in config["urls"]:
            print(f"   📄 {url}", flush=True)
            produits = scraper_rubrique(url, config)
            tous_produits.extend(produits)
            time.sleep(1)
        
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
                            if mettre_a_jour_prix_existant(sheet, row, prix_actuel, timestamp):
                                stats["modifies"] += 1
                                print(f"   📝 MAJ {produit['nom'][:40]} : {ancien_prix}€ → {prix_actuel}€", flush=True)
                        else:
                            stats["identiques"] += 1
            print(f"   ✅ {len(uniques)} produits trouvés", flush=True)
        else:
            print(f"   ⚠️ Aucun produit trouvé", flush=True)
    
    if nouvelles_lignes:
        print(f"\n📝 Ajout de {len(nouvelles_lignes)} nouveaux produits...", flush=True)
        for i, ligne in enumerate(nouvelles_lignes):
            if ajouter_avec_retry(sheet, ligne):
                if (i + 1) % 10 == 0:
                    print(f"   {i + 1}/{len(nouvelles_lignes)} lignes ajoutées...", flush=True)
            time.sleep(1)
        print(f"\n✅ {len(nouvelles_lignes)} nouveaux produits ajoutés", flush=True)
    
    print(f"\n📊 RÉSUMÉ:", flush=True)
    print(f"   🆕 Nouveaux: {stats['nouveaux']}", flush=True)
    print(f"   📝 Modifiés: {stats['modifies']}", flush=True)
    print(f"   🔄 Identiques: {stats['identiques']}", flush=True)
    colorer_fournisseurs_manuels(sheet)

# ==================== LANCER ====================
if __name__ == "__main__":
    print("\n" + "="*50, flush=True)
    print("📦 SCRAPING UNIFIÉ DES PRIX CONTAINERS", flush=True)
    print("="*50, flush=True)
    print(f"Heure de début: {datetime.now()}", flush=True)
    
    try:
        mettre_a_jour_prix()
        print("\n✅ Script terminé", flush=True)
    except Exception as e:
        print(f"\n❌ Erreur fatale: {e}", flush=True)
        import traceback
        traceback.print_exc()
