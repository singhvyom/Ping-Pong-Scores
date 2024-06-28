# 
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

def fetch_data():
    

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets"
    ]

    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)

    sheet_id = "10Wgin5jU40oUP5sSRo2HaR4NM4giDc56oCtMvqZJl8s"
    sheet = client.open_by_key(sheet_id)

    values_list = sheet.sheet1.get_all_values()
    scores = pd.DataFrame(values_list[1:], columns=values_list[0])
    scores['H'] = scores['H'].astype(int)
    scores['V'] = scores['V'].astype(int)
    scores = scores.dropna()
    # Calculate statistics
    stats = {
        'H': {
            'win_loss_record': int((scores['H'] > scores['V']).sum()),
            'average': float(scores['H'].mean()),
            'std_deviation': float(scores['H'].std()),
            'max': int(scores['H'].max()),
            'min': int(scores['H'].min())
        },
        'Vyom': {
            'win_loss_record': int((scores['V'] > scores['H']).sum()),
            'average': float(scores['V'].mean()),
            'std_deviation': float(scores['V'].std()),
            'max': int(scores['V'].max()),
            'min': int(scores['V'].min())
        }
    }
    
    return stats

if __name__ == "__main__":
    stats = fetch_data()
    #print(scores)


