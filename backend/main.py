from __future__ import annotations

from pathlib import Path

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

_REPO_ROOT = Path(__file__).resolve().parents[1]


def fetch_data():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    creds = Credentials.from_service_account_file(
        _REPO_ROOT / "credentials.json",
        scopes=scopes,
    )
    client = gspread.authorize(creds)

    sheet_id = os.getenv("SHEET_ID")
    sheet = client.open_by_key(sheet_id)

    values_list = sheet.sheet1.get_all_values()
    scores = pd.DataFrame(values_list[1:], columns=values_list[0])
    scores["H"] = scores["H"].astype(int)
    scores["V"] = scores["V"].astype(int)
    scores = scores.dropna()

    return {
        "H": {
            "win_loss_record": int((scores["H"] > scores["V"]).sum()),
            "average": float(scores["H"].mean()),
            "std_deviation": float(scores["H"].std()),
            "max": int(scores["H"].max()),
            "min": int(scores["H"].min()),
        },
        "Vyom": {
            "win_loss_record": int((scores["V"] > scores["H"]).sum()),
            "average": float(scores["V"].mean()),
            "std_deviation": float(scores["V"].std()),
            "max": int(scores["V"].max()),
            "min": int(scores["V"].min()),
        },
    }


if __name__ == "__main__":
    print(fetch_data())
