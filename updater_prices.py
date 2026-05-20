import requests
from bs4 import BeautifulSoup
import re
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import json
import time

# ==================== CONFIGURATION ====================
# 🔧 REMPLACE PAR L'ID DE TON GOOGLE SHEETS 🔧
SHEET_ID = "1XBidRt-lJX9zXD3ZCCWZ-A1xKiW9NVrM5sVRPM5wce4"  # ← Ton ID

# Nom de la feuille cible
FEUILLE_HISTORIQUE = "HistoriquePrix"

# Configuration des sites à scraper
SITES_CONFIG = {
    "Box'Innov": {
        "urls": ["https://www.boxinnov.com/conteneur-maritime/"],
        "regions": ["Lyon", "Nantes", "Marseille"],
        "type": "rubrique",
        "prix_pattern": r'(\d{1,3}(?:[\s]?\d{3})?)\s?[€&euro;]',
        "nom_selector": ["h2", "h3", ".product-title"],
        "source": "fournisseur_direct"
    },
    "Eurobox": {
        "urls": [
            "https://eurobox.fr/categorie-produit/containers/containers-maritime/",
            "https://eurobox.fr/categorie-produit/containers/containers-maritime/page/2/"
        ],
        "regions": ["Marseille (port)", "Nantes (port)", "Lyon (port)"],
        "type": "rubrique",
        "prix_pattern": r'(\d{1,3}(?:[\s]?\d{3})?)\s?[€&euro;]',
        "nom_selector": ["h2", "h3", ".product-title", "span"],
        "source": "fournisseur_direct"
    },
    "Cubner": {
        "urls": ["https://cubner.com/categorie-produit/conteneur-dry/"],
        "regions": ["Paris", "Lyon"],
        "type": "rubrique",
        "prix_pattern": r'(?:à partir de|dès)\s*(\d{1,3}(?:[\s]?\d{3})?)\s?[€&euro;]',
        "nom_selector": ["h2", "h3", ".product-title", ".title"],
        "source": "fournisseur_direct"
    },
    "MouvBox": {
        "urls": ["https://mouvbox-france.com/categorie-produit/containers/les-standards/"],
        "regions": ["Toulouse", "Perpignan"],
        "type": "rubrique",
        "prix_pattern": r'(?:dès|à partir de)\s*(\d{1,3}(?:[\s]?\d{3})?)\s?[€&euro;]',
        "nom_selector": ["h2", "h3", ".product-title"],
        "source": "fournisseur_direct"
    },
    "CFC": {
        "urls": ["https://compagnie-francaise-du-conteneur.fr/collections/standards"],
        "regions": ["Marseille", "Lyon", "Lille"],
        "type": "rubrique",
        "prix_pattern": r'À partir de\s*(\d{1,3}(?:[\s]?\d{3})?)[\s,]?(\d{2})?\s?[€&euro;]\s?TTC',
        "nom_selector": ["h2", "h3", ".product-title"],
        "source": "fournisseur_direct"
    },
    "ACM Container": {
        "urls": [
            "https://acm-container.fr/conteneurs-maritimes/neuf/",
            "https://acm-container.fr/conteneurs-maritimes/occasion/"
        ],
        "regions": ["Marseille"],
        "type": "rubrique",
        "prix_pattern": r'(?:à partir de|À partir de)\s*(\d{1,3}(?:[\s]?\d{3})?)\s?[€&euro;]',
        "nom_selector": ["h2", "h3", ".product-title"],
        "source": "fournisseur_direct"
    }
}

# Fournisseurs manuels (colorés en jaune)
FOURNISSEURS_MANUELS = [
    "Nord Container", "2M Containers", "Easy Container", "BBox Container",
    "Méditerranée Containers", "ABC Container", "Est Container", "Ouest Container",
    "IDF Containers", "Toulouse Container", "Resotainer", "TITAN Containers France",
    "Bluetainer", "ContainerZ", "Sea Box Company"
]

# ==================== CONNEXION GOOGLE SHEETS ====================
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
def scraper_rubrique(url, config):
    """Scrape les produits depuis une page rubrique"""
    produits = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Méthode 1 : Chercher par blocs
        for bloc in soup.find_all(['div', 'article'], class_=re.compile(r'product|item', re.I)):
            nom = None
            for selector in config["nom_selector"]:
                elem = bloc.find(selector)
                if elem:
                    nom = elem.get_text(strip=True)
                    if nom and len(nom) > 3:
                        break
            
            texte = bloc.get_text()
            match = re.search(config["prix_pattern"], texte, re.I)
            prix = match.group(1).replace(' ', '') if match else None
            
            if nom and prix and len(nom) > 3 and len(prix) > 2:
                produits.append({'nom': nom[:100], 'prix': int(prix)})
        
        # Méthode 2 : Recherche directe si pas assez de produits
        if len(produits) < 3:
            texte_page = soup.get_text()
            matches = re.findall(r'(?:(?:À partir de|dès|à partir de)\s*(\d{1,3}(?:[\s]?\d{3})?)\s?[€&euro;])', texte_page, re.I)
            if matches:
                for titre in soup.find_all(config["nom_selector"]):
                    nom = titre.get_text(strip=True)
                    if nom and len(nom) > 5:
                        produits.append({'nom': nom[:100], 'prix': int(matches[0].replace(' ', ''))})
        
        return produits
    except Exception as e:
        print(f"   Erreur scraping {url}: {e}")
        return []

# ==================== MISE À JOUR GOOGLE SHEETS ====================
def colorer_fournisseurs_manuels(sheet):
    """Colore en jaune les fournisseurs à saisie manuelle"""
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
        
        print(f"   🟡 {count} fournisseurs colorés en jaune")
    except Exception as e:
        print(f"   ⚠️ Erreur coloration: {e}")

def mettre_a_jour_prix():
    print("\n📂 Connexion à Google Sheets...")
    client = connecter_google_sheets()
    sheet = client.open_by_key(SHEET_ID).worksheet(FEUILLE_HISTORIQUE)
    
    nouvelles_lignes = []
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    for fournisseur, config in SITES_CONFIG.items():
        print(f"\n🔍 Scraping {fournisseur}...")
        tous_produits = []
        
        for url in config["urls"]:
            print(f"   📄 {url}")
            produits = scraper_rubrique(url, config)
            tous_produits.extend(produits)
            time.sleep(1)  # Pause entre les pages
        
        if tous_produits:
            # Supprimer les doublons (même nom)
            uniques = {}
            for p in tous_produits:
                if p['nom'] not in uniques or p['prix'] < uniques[p['nom']]['prix']:
                    uniques[p['nom']] = p
            
            for produit in uniques.values():
                for region in config["regions"]:
                    # Déterminer le type de container (optionnel)
                    type_container = "20_occ"
                    if "20" in produit['nom'] and "neuf" in produit['nom'].lower():
                        type_container = "20_neuf"
                    elif "40" in produit['nom'] and "neuf" in produit['nom'].lower():
                        type_container = "40_neuf"
                    elif "40" in produit['nom']:
                        type_container = "40_occ"
                    elif "20" in produit['nom']:
                        type_container = "20_occ"
                    
                    nouvelle_ligne = [
                        timestamp,           # Timestamp
                        fournisseur,         # Fournisseur
                        produit['nom'],      # Type Container
                        region,              # Région
                        type_container,      # Type Container (code)
                        produit['prix'],     # Prix TTC
                        0,                   # Livraison
                        "selon fournisseur", # Garantie
                        "variable",          # Délai
                        config["source"],    # Source
                        4.0                  # Note
                    ]
                    nouvelles_lignes.append(nouvelle_ligne)
            
            print(f"   ✅ {len(uniques)} produits trouvés → {len(uniques) * len(config['regions'])} lignes")
        else:
            print(f"   ⚠️ Aucun produit trouvé")
    
    # Ajouter les nouvelles lignes AVEC PAUSE pour éviter l'erreur 429
    if nouvelles_lignes:
        print(f"\n📝 Ajout de {len(nouvelles_lignes)} lignes...")
        for i, ligne in enumerate(nouvelles_lignes):
            try:
                sheet.append_row(ligne, value_input_option='USER_ENTERED')
                if (i + 1) % 10 == 0:
                    print(f"   {i + 1}/{len(nouvelles_lignes)} lignes ajoutées...")
                time.sleep(0.5)  # Pause de 0.5 seconde pour éviter le quota
            except Exception as e:
                print(f"   ⚠️ Erreur ligne {i+1}: {e}")
        
        print(f"\n✅ {len(nouvelles_lignes)} lignes ajoutées")
        colorer_fournisseurs_manuels(sheet)
    else:
        print("⚠️ Aucune donnée ajoutée")

# ==================== LANCER ====================
if __name__ == "__main__":
    print("\n" + "="*50)
    print("📦 SCRAPING UNIFIÉ DES PRIX CONTAINERS")
    print("="*50)
    mettre_a_jour_prix()
    print("\n✅ Script terminé")
