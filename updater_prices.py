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
SHEET_ID = "1kdZFXQKBo2Hom880XpuvtksrsVo3nswmOaL4Cc-hv1Y"

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
    
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    
    if not creds_json:
        raise Exception("❌ Variable GOOGLE_CREDENTIALS non définie")
    
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

# ==================== SCRAPING AMÉLIORÉ ====================
def scraper_leboncoin(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fr,fr-FR;q=0.8,en;q=0.5',
        }
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        prix_elements = soup.select('[data-test-id="price"], .price, .ProductPrice')
        prix = []
        for el in prix_elements[:5]:
            texte = re.sub(r'[^0-9]', '', el.text)
            if texte and len(texte) > 2:
                prix.append(int(texte))
        
        if not prix:
            texte_page = soup.get_text()
            matches = re.findall(r'(\d{4,5})\s?[€]', texte_page)
            if matches:
                prix = [int(m) for m in matches[:5]]
        
        return min(prix) if prix else None
    except Exception as e:
        print(f"   Erreur: {e}")
        return None

def scraper_ebay(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
        }
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        prix_elements = soup.select('.s-item__price, .vi-price, .x-price-primary')
        prix = []
        for el in prix_elements[:5]:
            texte = re.sub(r'[^0-9]', '', el.text)
            if texte and len(texte) > 2:
                prix.append(int(texte))
        
        return min(prix) if prix else None
    except:
        return None

def scraper_manomano(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
        }
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        selecteurs = ['.product-price', '.price', '.js-price', '[data-price]']
        for sel in selecteurs:
            elements = soup.select(sel)
            for el in elements:
                texte = re.sub(r'[^0-9]', '', el.text)
                if texte and len(texte) > 2:
                    return int(texte)
        return None
    except:
        return None

def scraper_amazon(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
        }
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        prix_elements = soup.select('.a-price-whole, .a-offscreen')
        for el in prix_elements[:5]:
            texte = re.sub(r'[^0-9]', '', el.text)
            if texte and len(texte) > 2:
                return int(texte)
        return None
    except:
        return None

# ==================== COLORATION DES FOURNISSEURS MANUELS ====================
def colorer_fournisseurs_manuels():
    """Colore en jaune les fournisseurs à saisie manuelle dans Google Sheets"""
    
    print("🎨 Coloration des fournisseurs manuels...")
    client = connecter_google_sheets()
    sheet = client.open_by_key(SHEET_ID).worksheet(FEUILLE_HISTORIQUE)
    
    toutes_les_lignes = sheet.get_all_values()
    
    if not toutes_les_lignes:
        print("   Aucune donnée trouvée")
        return
    
    # Trouver la colonne Fournisseur
    entetes = toutes_les_lignes[0]
    col_fournisseur = None
    for i, col in enumerate(entetes):
        if col.lower() == "fournisseur":
            col_fournisseur = i + 1  # 1-indexé pour gspread
            break
    
    if not col_fournisseur:
        print("   ❌ Colonne 'Fournisseur' non trouvée")
        return
    
    # Couleur jaune
    yellow_format = {
        "backgroundColor": {
            "red": 1.0,
            "green": 1.0,
            "blue": 0.6
        }
    }
    
    count = 0
    for row in range(2, len(toutes_les_lignes) + 1):
        fournisseur = sheet.cell(row, col_fournisseur).value
        if fournisseur in FOURNISSEURS_MANUELS:
            sheet.format(f"{chr(64 + col_fournisseur)}{row}", yellow_format)
            count += 1
            print(f"   🟡 {fournisseur} coloré")
    
    print(f"✅ {count} fournisseurs colorés en jaune")

# ==================== MISE À JOUR GOOGLE SHEETS ====================
def mettre_a_jour_prix_auto():
    """Scrape les prix et met à jour Google Sheets"""
    
    print("📂 Connexion à Google Sheets...")
    client = connecter_google_sheets()
    sheet = client.open_by_key(SHEET_ID).worksheet(FEUILLE_HISTORIQUE)
    
    toutes_les_lignes = sheet.get_all_values()
    entetes = toutes_les_lignes[0]
    
    col_url = None
    for i, col in enumerate(entetes):
        if col.lower() == "url":
            col_url = i + 1
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
                    timestamp, fournisseur, "all", type_container,
                    prix_ajuste, 0, "selon vendeur", "variable",
                    "marketplace", 4.0, 0
                ]
                
                if col_url:
                    nouvelle_ligne.append(url)
                
                nouveaux_prix.append(nouvelle_ligne)
            
            print(f"   ✅ Prix trouvé: {prix}€")
        else:
            print(f"   ⚠️ Aucun prix trouvé")
        
        time.sleep(2)
    
    if nouveaux_prix:
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
        nouvelle_entete = entetes + ["URL"]
        sheet.update('A1:Z1', [nouvelle_entete])
        print("✅ Colonne 'URL' ajoutée")
    else:
        print("✅ Colonne 'URL' existe déjà")

# ==================== LANCER ====================
if __name__ == "__main__":
    import sys
    
    print("\n" + "="*50)
    print("📦 MISE À JOUR AUTOMATIQUE DES PRIX")
    print("="*50)
    
    if len(sys.argv) > 1:
        choix = sys.argv[1]
    else:
        choix = "1"
    
    if choix == "1":
        mettre_a_jour_prix_auto()
    elif choix == "2":
        afficher_statut()
    elif choix == "3":
        ajouter_colonne_url()
    elif choix == "4":
        colorer_fournisseurs_manuels()
    else:
        print("Choix invalide")
