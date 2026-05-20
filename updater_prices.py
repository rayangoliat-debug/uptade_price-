import gspread
from google.oauth2.service_account import Credentials
from bs4 import BeautifulSoup
import re
import requests
from datetime import datetime
import os
import json

# ==================== CONFIGURATION ====================
# 🔧 REMPLACE CET ID PAR LE TIEN 🔧
SHEET_ID = "1kdZFXQKBo2Hom880XpuvtksrsVo3nswmOaL4Cc-hv1YY" 

# Nom de la feuille à mettre à jour
FEUILLE_HISTORIQUE = "HistoriquePrix"

# Sites à scraper
SITES_A_SCRAPER = {
    "Box'Innov": {
        "url": "https://www.boxinnov.com/conteneurs-maritimes/conteneur-6-pieds-dry/",
        "type": "unitaire",
        "selecteur_prix": ".price, .product-price",
        "selecteur_nom": "h1, .product-title",
        "region": "all",
        "source": "fournisseur_direct"
    },
    "CFC": {
        "url": "https://compagnie-francaise-du-conteneur.fr/produits/20-pieds-dry",
        "type": "generique",
        "motif_prix": r"(\d{1,3}(?:[\s]?\d{3})?)\s?[€&euro;]\s?TTC",
        "selecteur_nom": "h1, .product-title",
        "region": "all",
        "source": "fournisseur_direct"
    },
    "Eurobox": {
        "url": "https://eurobox.fr/categorie-produit/containers/containers-maritime/",
        "type": "generique",
        "motif_prix": r"(\d{1,3}(?:[\s]?\d{3})?)\s?[€&euro;]\s?HT",
        "selecteur_nom": "h2, h3, .product-title",
        "region": "all",
        "source": "fournisseur_direct"
    },
    "MouvBox": {
        "url": "https://mouvbox-france.com/categorie-produit/containers/les-standards/",
        "type": "generique",
        "motif_prix": r"(?:dès|à partir de)\s*(\d{1,3}(?:[\s]?\d{3})?)\s?[€&euro;]",
        "selecteur_nom": "h2, h3, .product-title",
        "region": "all",
        "source": "fournisseur_direct"
    },
    "Cubner": {
        "url": "https://cubner.com/categorie-produit/conteneur-dry/",
        "type": "generique",
        "motif_prix": r"(?:à partir de|dès)\s*(\d{1,3}(?:[\s]?\d{3})?)\s?[€&euro;]",
        "selecteur_nom": "h2, h3, .product-title",
        "region": "all",
        "source": "fournisseur_direct"
    }
}

# Fournisseurs à colorer en jaune (saisie manuelle)
FOURNISSEURS_MANUELS = [
    "Nord Container", "2M Containers", "Easy Container", "BBox Container",
    "Méditerranée Containers", "ABC Container", "Est Container", "Ouest Container",
    "IDF Containers", "Toulouse Container", "Resotainer", "TITAN Containers France",
    "Bluetainer", "ContainerZ", "Sea Box Company"
]

# ==================== CONNEXION GOOGLE SHEETS ====================
def connecter_google_sheets():
    """Se connecte à Google Sheets via variable d'environnement"""
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    else:
        # Pour le test local
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    
    return gspread.authorize(creds)

# ==================== FONCTIONS DE SCRAPING ====================
def get_nom_produit(soup, selecteur):
    """Extrait le nom du produit"""
    try:
        if selecteur:
            elements = soup.select(selecteur)
            for el in elements:
                nom = el.get_text(strip=True)
                if nom and len(nom) > 3:
                    return nom[:100]
        titre = soup.find('title')
        if titre:
            return titre.get_text(strip=True)[:100]
        return "Container standard"
    except:
        return "Container standard"

def scraper_boxinnov(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        texte = soup.get_text()
        match = re.search(r'(\d{1,3}(?:[\s]?\d{3})?)\s?[€&euro;]', texte)
        prix = int(match.group(1).replace(' ', '')) if match else None
        nom = get_nom_produit(soup, "h1, .product-title, .title")
        return prix, nom
    except:
        return None, None

def scraper_site_generique(config):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(config["url"], headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        texte = soup.get_text()
        match = re.search(config["motif_prix"], texte, re.I)
        prix = int(match.group(1).replace(' ', '')) if match else None
        
        noms_produits = []
        for sel in ["h1", "h2", "h3", ".product-title", ".title"]:
            for el in soup.select(sel):
                nom = el.get_text(strip=True)
                if nom and len(nom) > 5 and len(nom) < 100:
                    if any(mot in nom.lower() for mot in ['container', 'conteneur', 'pieds', 'dry']):
                        noms_produits.append(nom)
        
        noms_produits = list(dict.fromkeys(noms_produits))
        if not noms_produits:
            noms_produits = ["Container standard"]
        
        return prix, noms_produits[:5]
    except:
        return None, []

# ==================== MISE À JOUR GOOGLE SHEETS ====================
def colorer_fournisseurs_manuels(sheet):
    """Colore en jaune les fournisseurs à saisie manuelle"""
    try:
        # Récupérer toutes les données
        data = sheet.get_all_values()
        
        if len(data) <= 1:
            return
        
        # Trouver la colonne Fournisseur
        entetes = data[0]
        col_fournisseur = None
        for i, col in enumerate(entetes):
            if col.lower() == "fournisseur":
                col_fournisseur = i + 1
                break
        
        if not col_fournisseur:
            print("   ❌ Colonne 'Fournisseur' non trouvée")
            return
        
        # Appliquer la couleur jaune
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
    """Scrape tous les sites et met à jour Google Sheets"""
    
    print("\n📂 Connexion à Google Sheets...")
    client = connecter_google_sheets()
    sheet = client.open_by_key(SHEET_ID).worksheet(FEUILLE_HISTORIQUE)
    
    # Récupérer l'entête
    entetes = sheet.row_values(1)
    
    # Préparer les nouvelles lignes
    nouvelles_lignes = []
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    for fournisseur, config in SITES_A_SCRAPER.items():
        print(f"\n🔍 Scraping {fournisseur}...")
        
        if config["type"] == "unitaire":
            prix, nom = scraper_boxinnov(config["url"])
            noms_produits = [nom] if nom else ["Container"]
        else:
            prix, noms_produits = scraper_site_generique(config)
        
        if prix:
            for nom_produit in noms_produits:
                # Déterminer le type de container
                type_container = "20_occ"
                if "20" in nom_produit and "neuf" in nom_produit.lower():
                    type_container = "20_neuf"
                elif "40" in nom_produit and "neuf" in nom_produit.lower():
                    type_container = "40_neuf"
                elif "40" in nom_produit:
                    type_container = "40_occ"
                elif "20" in nom_produit:
                    type_container = "20_occ"
                
                nouvelle_ligne = [
                    timestamp,           # Timestamp
                    fournisseur,         # Fournisseur
                    nom_produit,         # Produit
                    config["region"],    # Région
                    type_container,      # Type Container
                    prix,                # Prix TTC
                    0,                   # Livraison
                    "selon fournisseur", # Garantie
                    "variable",          # Délai
                    config["source"],    # Source
                    4.0                  # Note
                ]
                nouvelles_lignes.append(nouvelle_ligne)
            print(f"   ✅ Prix trouvé: {prix}€ - {len(noms_produits)} produits")
        else:
            print(f"   ⚠️ Aucun prix trouvé")
    
    # Ajouter les nouvelles lignes au sheet
    if nouvelles_lignes:
        for ligne in nouvelles_lignes:
            sheet.append_row(ligne, value_input_option='USER_ENTERED')
        print(f"\n✅ {len(nouvelles_lignes)} prix ajoutés")
        
        # Colorer les fournisseurs manuels
        colorer_fournisseurs_manuels(sheet)
    else:
        print("⚠️ Aucun prix ajouté")

# ==================== LANCER ====================
if __name__ == "__main__":
    print("\n" + "="*50)
    print("📦 SCRAPING DES PRIX CONTAINERS")
    print("="*50)
    
    mettre_a_jour_prix()
    print("\n✅ Script terminé")
