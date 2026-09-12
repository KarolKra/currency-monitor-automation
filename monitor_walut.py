import requests
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
import smtplib
import ssl
from email.message import EmailMessage

def pobierz_dane_nbp(kod_waluty: str = "USD", dni: int = 90, okno_sredniej: int = 30) -> pd.DataFrame:
    """
    Pobiera historyczne kursy waluty z API NBP i oblicza średnią kroczącą (SMA).

    Funkcja łączy się z darmowym API Narodowego Banku Polskiego, pobiera kursy 
    średnie (Tabela A) z podanej liczby ostatnich dni, a następnie ładuje je 
    do ramki danych Pandas i wylicza prostą średnią kroczącą.

    Args:
        kod_waluty (str): Trzyliterowy kod waluty w standardzie ISO 4217 (domyślnie "USD").
        dni (int): Liczba ostatnich dni roboczych do pobrania (domyślnie 90).
        okno_sredniej (int): Liczba dni do obliczenia średniej kroczącej (domyślnie 30).

    Returns:
        pd.DataFrame: Ramka danych z kolumnami: 'Data', 'Kurs', 'Srednia_X_dni'.
                      W przypadku błędu zapytania do API zwraca wartość None.
    """
    
    # 1. Budowa dynamicznego adresu URL do API NBP
    url = f"http://api.nbp.pl/api/exchangerates/rates/a/{kod_waluty}/last/{dni}/?format=json"
    
    try:
        # 2. Wysłanie zapytania GET i weryfikacja statusu odpowiedzi
        response = requests.get(url)
        response.raise_for_status() # Wyrzuci błąd, jeśli strona nie odpowie 200 OK
        dane_json = response.json()
        
        # 3. Wyciągnięcie listy kursów z JSON i konwersja na obiekt DataFrame
        df = pd.DataFrame(dane_json['rates'])
        
        # 4. Czyszczenie danych: wybór kolumn i zmiana nazw na polskie
        df = df[['effectiveDate', 'mid']]
        df.columns = ['Data', 'Kurs']
        
        # Konwersja kolumny z datą ze zwykłego tekstu (string) na obiekt datetime
        df['Data'] = pd.to_datetime(df['Data'])
        
        # 5. Logika biznesowa: Obliczenie średniej kroczącej za pomocą Pandas
        nazwa_kolumny_sma = f'Srednia_{okno_sredniej}_dni'
        df[nazwa_kolumny_sma] = df['Kurs'].rolling(window=okno_sredniej).mean()
        
        return df
        
    except requests.exceptions.RequestException as e:
        # Obsługa błędów, by program się nie zawiesił przy braku internetu
        print(f"Wystąpił błąd podczas połączenia z API NBP: {e}")
        return None

def sprawdz_sygnal_zakupu(df: pd.DataFrame, okno_sredniej: int = 30) -> bool:
    """
    Sprawdza, czy obecny kurs waluty wygenerował sygnał do zakupu.

    Funkcja analizuje ostatni dostępny wiersz z ramki danych. Jeśli 
    aktualny kurs jest mniejszy niż średnia krocząca z ostatnich X dni, 
    oznacza to, że waluta jest statystycznie tania (okazja).

    Args:
        df (pd.DataFrame): Ramka danych z kolumnami 'Kurs' i 'Srednia_X_dni'.
        okno_sredniej (int): Liczba dni użyta wcześniej do średniej (domyślnie 30).

    Returns:
        bool: True, jeśli wystąpił sygnał zakupu. False w przeciwnym razie.
    """
    ostatni_wiersz = df.iloc[-1]
    aktualny_kurs = ostatni_wiersz['Kurs']
    aktualna_srednia = ostatni_wiersz[f'Srednia_{okno_sredniej}_dni']
    
    return aktualny_kurs < aktualna_srednia


def wygeneruj_wykres(df: pd.DataFrame, kod_waluty: str = "USD", okno_sredniej: int = 30) -> str:
    """
    Generuje wykres kursu waluty wraz ze średnią kroczącą i zapisuje go do pliku.

    Rysuje liniowy wykres kursu oraz nałożoną na niego linię średniej SMA.
    Używa biblioteki Seaborn do nadania profesjonalnego stylu. Wynik 
    jest zapisywany jako plik PNG, gotowy do wysłania mailem.

    Args:
        df (pd.DataFrame): Ramka danych zawierająca kolumny 'Data', 'Kurs' oraz SMA.
        kod_waluty (str): Kod waluty do tytułu wykresu (domyślnie "USD").
        okno_sredniej (int): Wartość okna średniej dla legendy (domyślnie 30).

    Returns:
        str: Ścieżka do utworzonego pliku z wykresem (np. 'wykres_USD.png').
    """
    sns.set_theme(style="darkgrid")
    plt.figure(figsize=(10, 6))
    
    # Rysowanie głównego kursu i średniej
    plt.plot(df['Data'], df['Kurs'], label=f'Kurs {kod_waluty}', color='royalblue', linewidth=2)
    
    nazwa_kolumny_sma = f'Srednia_{okno_sredniej}_dni'
    plt.plot(df['Data'], df[nazwa_kolumny_sma], label=f'Średnia {okno_sredniej}-dniowa', 
             color='darkorange', linestyle='--', linewidth=2)
    
    # Formatowanie wykresu
    plt.title(f'Analiza kursu {kod_waluty} - Automatyczny Raport', fontsize=14, fontweight='bold')
    plt.xlabel('Data', fontsize=12)
    plt.ylabel('Kurs (PLN)', fontsize=12)
    plt.legend(loc='best')
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Zapis obrazka na dysku
    nazwa_pliku = f'wykres_{kod_waluty}.png'
    plt.savefig(nazwa_pliku, dpi=300)
    plt.close() # Zamknięcie figury czyści pamięć RAM
    
    return nazwa_pliku

def wyslij_raport_email(nadawca: str, haslo: str, odbiorca: str, waluta: str, czy_okazja: bool, sciezka_wykresu: str) -> bool:
    """
    Wysyła automatyczną wiadomość e-mail z powiadomieniem o kursie i załączonym wykresem.

    Funkcja loguje się na serwer SMTP (domyślnie Gmail), tworzy wiadomość
    z odpowiednim tematem i treścią w zależności od tego, czy wystąpił sygnał
    zakupowy, a następnie dołącza wygenerowany wcześniej plik graficzny z wykresem.

    Args:
        nadawca (str): Adres e-mail nadawcy (np. na Gmailu).
        haslo (str): 16-znakowe hasło do aplikacji (wygenerowane w Google).
        odbiorca (str): Adres e-mail, na który ma trafić raport.
        waluta (str): Kod analizowanej waluty (np. "USD").
        czy_okazja (bool): Prawda/Fałsz w zależności od sygnału z algorytmu.
        sciezka_wykresu (str): Ścieżka do pliku PNG, który ma zostać załączony.

    Returns:
        bool: True, jeśli wiadomość została wysłana pomyślnie. False w przypadku błędu.
    """
    # 1. Konstrukcja wiadomości e-mail
    msg = EmailMessage()
    
    # Dynamiczny temat i treść w zależności od tego, czy opłaca się kupować
    if czy_okazja:
        msg['Subject'] = f"🔔 OKAZJA: Kurs {waluta} spadł poniżej średniej 30-dniowej!"
        tresc = f"Cześć,\n\nNasz algorytm wykrył, że kurs {waluta} jest dzisiaj poniżej swojej 30-dniowej średniej kroczącej.\nTo statystycznie dobry moment na wymianę waluty.\n\nW załączniku znajdziesz szczegółowy wykres."
    else:
        msg['Subject'] = f"📊 Dzienny raport kursu {waluta} - brak sygnału do zakupu"
        tresc = f"Cześć,\n\nDzisiejszy kurs {waluta} utrzymuje się powyżej średniej kroczącej. Zgodnie z algorytmem, sugerujemy wstrzymanie się z zakupami.\n\nW załączniku przesyłam aktualny wykres analizy."
        
    msg['From'] = nadawca
    msg['To'] = odbiorca
    msg.set_content(tresc)

    # 2. Odczytanie obrazka z dysku i załączenie go do maila
    if os.path.exists(sciezka_wykresu):
        with open(sciezka_wykresu, 'rb') as f:
            plik_dane = f.read()
            nazwa_pliku = os.path.basename(sciezka_wykresu)
            
        # Dołączenie pliku jako obrazu PNG
        msg.add_attachment(plik_dane, maintype='image', subtype='png', filename=nazwa_pliku)
    else:
        print(f"Ostrzeżenie: Nie znaleziono pliku {sciezka_wykresu}. Wysyłam maila bez załącznika.")

    # 3. Nawiązanie bezpiecznego połączenia z serwerem i wysłanie
    kontekst = ssl.create_default_context()
    
    try:
        print("Łączenie z serwerem pocztowym...")
        # Adres i port poniżej są standardowe dla poczty Gmail
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=kontekst) as serwer:
            serwer.login(nadawca, haslo)
            serwer.send_message(msg)
        return True
    except Exception as e:
        print(f"Błąd podczas wysyłania e-maila. Sprawdź poprawność hasła aplikacji. Szczegóły: {e}")
        return False

# --- GŁÓWNA LOGIKA SKRYPTU (ENTRY POINT) ---
# Kod uruchomi się automatycznie przy bezpośrednim wywołaniu (np. przez Harmonogram Zadań)
if __name__ == "__main__":
    # ZMIENNE DO KONFIGURACJI - Podmień na własne!
    WALUTA = "USD"
    TWOJ_EMAIL = "adres@gmail.com"  # Wpisz swój email
    TWOJ_EMAIL_ODBIORCY = "adres@gmail.com" # Możesz wysłać maila sam do siebie
    HASLO_APLIKACJI = "tutaj_wklej_16_znakowe_haslo_z_google" 
    
    # KROK 1: Pobieranie danych
    df_dane = pobierz_dane_nbp(WALUTA, 90, 30)
    
    if df_dane is not None:
        # KROK 2: Analiza danych i szukanie sygnału
        czy_kupowac = sprawdz_sygnal_zakupu(df_dane)
        if czy_kupowac:
            print(f"Zanotowano sygnał zakupu dla waluty {WALUTA}.")
        else:
            print(f"Brak sygnału zakupu dla waluty {WALUTA}.")
            
        # KROK 3: Wygenerowanie wykresu na dysk
        sciezka = wygeneruj_wykres(df_dane, WALUTA)
        print(f"Zapisano wykres: {sciezka}")
        
        # KROK 4: Wysłanie powiadomienia e-mail z załącznikiem
        sukces = wyslij_raport_email(TWOJ_EMAIL, HASLO_APLIKACJI, TWOJ_EMAIL_ODBIORCY, WALUTA, czy_kupowac, sciezka)
        
        if sukces:
            print("SUKCES: Cały proces zakończony! E-mail został wysłany.")
        else:
            print("PROCES ZAKOŃCZONY BŁĘDEM: Nie udało się wysłać e-maila.")