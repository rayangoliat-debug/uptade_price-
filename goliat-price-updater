import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re
import time
import os
import json

# ==================== CONFIGURATION ====================
# ID du Google Sheets (à modifier)
SHEET_ID = "1kdZFXQKBo2Hom880XpuvtksrsVo3nswmOaL4Cc-hv1Y"  # ← ID du fichier Google Sheets

# Nom de la feuille
FEUILLE_HISTORIQUE = "HistoriquePrix"

# URLs exploitables (scraping automatique)
URLS_AUTO = {
    "LeBonCoin Marketplace": "https://www.leboncoin.fr/recherche?text=container+occasion",
    "eBay France": "https://www.ebay.fr/sch/i.html?_nkw=container+occasion",
    "ManoMano": "https://www.manomano.fr/cat/container+stockage",
    "Amazon Business": "https://www.amazon.fr/s?k=container+occasion"
}

# Fournisseurs qui nécessitent une saisie manuelle
FOURNISSEURS_MANUELS = [
    "Nord Container", "2M Containers", "Easy Container", "BBox Container",
    "Méditerranée Containers", "ABC Container", "Est Container", "Ouest Container",
    "IDF Containers", "Toulouse Container"
]

# ==================== CONNEXION GOOGLE SHEETS ====================
def connecter_google_sheets():
    """Se connecte à Google Sheets via variable d'environnement"""
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # Lire la clé depuis la variable d'environnement
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    
    if not creds_json:
        raise Exception("❌ Variable GOOGLE_CREDENTIALS non définie")
    
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

# ==================== SCRAPING ====================
def scraper_leboncoin(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        prix_elements = soup.select('[data-test-id="price"]')
        prix = []
        for el in prix_elements[:3]:
            texte = re.sub(r'[^0-9]', '', el.text)
            if texte:
                prix.append(int(texte))
        return min(prix) if prix else None
    except:
        return None

def scraper_ebay(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        prix_elements = soup.select('.s-item__price')
        prix = []
        for el in prix_elements[:3]:
            texte = re.sub(r'[^0-9]', '', el.text)
            if texte:
                prix.append(int(texte))
        return min(prix) if prix else None
    except:
        return None

def scraper_manomano(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        prix_element = soup.select_one('.product-price')
        if prix_element:
            texte = re.sub(r'[^0-9]', '', prix_element.text)
            return int(texte) if texte else None
        return None
    except:
        return None

def scraper_amazon(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        prix_element = soup.select_one('.a-price-whole')
        if prix_element:
            return int(prix_element.text.replace(',', ''))
        return None
    except:
        return None

# ==================== MISE À JOUR GOOGLE SHEETS ====================
def mettre_a_jour_prix_auto():
    """Scrape les prix et met à jour Google Sheets"""
    
    print("📂 Connexion à Google Sheets...")
    client = connecter_google_sheets()
    sheet = client.open_by_key(SHEET_ID).worksheet(FEUILLE_HISTORIQUE)
    
    # Récupérer toutes les données
    toutes_les_lignes = sheet.get_all_values()
    entetes = toutes_les_lignes[0]
    
    # Trouver l'index de la colonne URL si elle existe
    col_url = None
    for i, col in enumerate(entetes):
        if col.lower() == "url":
            col_url = i + 1  # 1-indexé pour gspread
            break
    
    nouveaux_prix = []
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    scraper_functions = {
        "LeBonCoin Marketplace": scraper_leboncoin,
        "eBay France": scraper_ebay,
        "ManoMano": scraper_manomano,
        "Amazon Business": scraper_amazon
    }
    
    for fournisseur, scraper_func in scraper_functions.items():
        if fournisseur not in URLS_AUTO:
            continue
        
        url = URLS_AUTO[fournisseur]
        print(f"🔍 Scraping {fournisseur}...")
        prix = scraper_func(url)
        
        if prix:
            # Ajustement selon le type de container
            for type_container in ["20_occ", "20_neuf", "40_occ", "40_neuf"]:
                if type_container == "20_neuf":
                    prix_ajuste = int(prix * 1.8)
                elif type_container == "40_occ":
                    prix_ajuste = int(prix * 1.5)
                elif type_container == "40_neuf":
                    prix_ajuste = int(prix * 2.2)
                else:
                    prix_ajuste = prix
                
                nouvelle_ligne = [
                    timestamp,
                    fournisseur,
                    "all",
                    type_container,
                    prix_ajuste,
                    0,
                    "selon vendeur",
                    "variable",
                    "marketplace",
                    4.0,
                    0
                ]
                
                # Ajouter l'URL si la colonne existe
                if col_url:
                    nouvelle_ligne.append(url)
                
                nouveaux_prix.append(nouvelle_ligne)
            
            print(f"   ✅ Prix trouvé: {prix}€")
        else:
            print(f"   ⚠️ Aucun prix trouvé")
        
        time.sleep(2)
    
    if nouveaux_prix:
        # Ajouter les nouvelles lignes à la fin
        for ligne in nouveaux_prix:
            sheet.append_row(ligne, value_input_option='USER_ENTERED')
        
        print(f"\n✅ {len(nouveaux_prix)} prix automatiques ajoutés")
    else:
        print("⚠️ Aucun prix automatique ajouté")

def afficher_statut():
    """Affiche les fournisseurs manquants"""
    
    print("\n" + "="*50)
    print("📊 STATUT DES FOURNISSEURS")
    print("="*50)
    
    for fournisseur in FOURNISSEURS_MANUELS:
        print(f"🟡 {fournisseur}: à mettre à jour manuellement")
    
    print("\n✅ Fournisseurs automatiques :")
    for fournisseur in URLS_AUTO.keys():
        print(f"   🤖 {fournisseur}")

def ajouter_colonne_url():
    """Ajoute la colonne URL si elle n'existe pas"""
    
    client = connecter_google_sheets()
    sheet = client.open_by_key(SHEET_ID).worksheet(FEUILLE_HISTORIQUE)
    
    entetes = sheet.row_values(1)
    
    if "URL" not in entetes:
        # Ajouter la colonne URL à la fin
        nouvelle_entete = entetes + ["URL"]
        sheet.update('A1:Z1', [nouvelle_entete])
        print("✅ Colonne 'URL' ajoutée")
    else:
        print("✅ Colonne 'URL' existe déjà")

# ==================== LANCER ====================
if __name__ == "__main__":
    print("\n" + "="*50)
    print("📦 GESTION DES PRIX (Google Sheets)")
    print("="*50)
    print("\n1. Scraper les prix automatiques (marketplaces)")
    print("2. Afficher le statut des fournisseurs")
    print("3. Ajouter la colonne URL")
    
    choix = input("\nChoix (1/2/3): ")
    
    if choix == "1":
        mettre_a_jour_prix_auto()
    elif choix == "2":
        afficher_statut()
    elif choix == "3":
        ajouter_colonne_url()
    else:
        print("Choix invalide")
