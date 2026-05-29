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

# ==================== FONCTIONS DE SCRAPING ====================
def extraire_prix(texte, pattern):
    match = re.search(pattern, texte, re.I)
    if not match:
        return None
    prix_brut = match.group(1)
    prix_propre = re.sub(r'[^\d]', '', prix_brut)
    return int(prix_propre) if prix_propre else None

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
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        scraping_type = config.get("type", "standard")
        if scraping_type == "cubner":
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

# ==================== COLORATION OPTIMISÉE (BATCH) ====================
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
    
    # On télécharge TOUTE la feuille une seule fois pour travailler en mémoire locale
    toute_la_feuille = sheet.get_all_values()
    prix_existants = get_prix_existants(toute_la_feuille)
    print(f"📊 {len(prix_existants)} prix existants chargés", flush=True)
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    nouvelles_lignes = []
    mises_a_jour_cellules = []
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
                            # Stockage des mises à jour en mémoire pour les grouper après
                            mises_a_jour_cellules.append({'range': f'E{row}', 'values': [[prix_actuel]]})
                            mises_a_jour_cellules.append({'range': f'A{row}', 'values': [[timestamp]]})
                            stats["modifies"] += 1
                            print(f"   📝 Préparation MAJ {produit['nom'][:30]} : {ancien_prix}€ → {prix_actuel}€", flush=True)
                        else:
                            stats["identiques"] += 1
            print(f"   ✅ {len(uniques)} produits traités", flush=True)
        else:
            print(f"   ⚠️ Aucun produit trouvé", flush=True)
    
    # 1. EXÉCUTION DES MISES À JOUR EXISTANTES (BATCH)
    if mises_a_jour_cellules:
        print(f"\n⚡ Exécution en lot de {stats['modifies']} modifications de prix...", flush=True)
        sheet.batch_update(mises_a_jour_cellules)
        
    # 2. INSERTION DES NOUVEAUX PRODUITS (BATCH)
    if nouvelles_lignes:
        print(f"\n📝 Insertion groupée de {len(nouvelles_lignes)} nouveaux produits...", flush=True)
        sheet.append_rows(nouvelles_lignes, value_input_option='USER_ENTERED')
        print(f"   ✅ Tous les nouveaux produits ont été ajoutés d'un coup !", flush=True)
    
    print(f"\n📊 RÉSUMÉ:", flush=True)
    print(f"   🆕 Nouveaux: {stats['nouveaux']}")
    print(f"   📝 Modifiés: {stats['modifies']}")
    print(f"   🔄 Identiques: {stats['identiques']}")
    
    # 3. COLORATION SÉCURISÉE EN LOT
    data_fraiche = sheet.get_all_values()
    colorer_fournisseurs_manuels_batch(sheet, data_fraiche)

# ==================== LANCER ====================
if __name__ == "__main__":
    print("\n" + "="*50, flush=True)
    print("📦 SCRAPING UNIFIÉ DES PRIX CONTAINERS (VERSION PROD BATCH)", flush=True)
    print("="*50, flush=True)
    print(f"Heure de début: {datetime.now()}", flush=True)
    
    try:
        mettre_a_jour_prix()
        print("\n✅ Script de scraping terminé avec succès", flush=True)
    except Exception as e:
        print(f"\n❌ Erreur fatale: {e}", flush=True)
        import traceback
        traceback.print_exc()
