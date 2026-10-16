import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def fetch_due_cards(database_id):
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    
    # Get today's date in YYYY-MM-DD format
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    payload = {
        "filter": {
            "or": [
                {
                    "property": "next_review_date",
                    "date": {
                        "on_or_before": today_str
                    }
                },
                {
                    "property": "next_review_date",
                    "date": {
                        "is_empty": True
                    }
                }
            ]
        }
    }
    
    response = requests.post(url, json=payload, headers=HEADERS)
    
    if response.status_code != 200:
        print(f"Error fetching data: {response.status_code}")
        print(response.json())
        return []

    results = response.json().get("results", [])
    due_cards = []
    
    for row in results:
        # Safely extract data from Notion's nested JSON structure
        props = row["properties"]

        # Dynamically find the Title property (handles both "Lemma" and "Lemma / Past 3MS")
        lemma = ""
        for prop_name, prop_data in props.items():
            if prop_data["type"] == "title":
                if prop_data["title"]:
                    lemma = prop_data["title"][0]["plain_text"]
                break
                
        if not lemma:
            continue
        
        # Safely get text fields, defaulting to empty string if missing
        meaning = props["meaning"]["rich_text"][0]["plain_text"] if props["meaning"]["rich_text"] else ""

        # Extract Plural
        try:
            # Step 1: Check if the column exists. (Throws KeyError if it's a Verb)
            plural_col = props["plural_form"]
            try:
                # Step 2: Extract the text. (Throws IndexError if the cell is blank)
                plural = plural_col["rich_text"][0]["text"]["content"]
            except IndexError:
                plural = "" # Column exists but is blank
        except KeyError:
            plural = None # Column does not exist at all

        # Extract Present
        try:
            # Step 1: Check if the column exists. (Throws KeyError if it's a Noun)
            present_col = props["present_3ms"]
            try:
                # Step 2: Extract the text. (Throws IndexError if the cell is blank)
                present = present_col["rich_text"][0]["text"]["content"]
            except IndexError:
                present = "" # Column exists but is blank
        except KeyError:
            present = None # Column does not exist at all
        
        # Safely get number fields, defaulting to SM-2 baselines if empty
        next_review_date = props["next_review_date"]["date"]["start"] if props["next_review_date"]["date"]["start"] is not None else "9999-12-31"
        interval = props["interval"]["number"] if props["interval"]["number"] is not None else 0
        ease = props["ease_factor"]["number"] if props["ease_factor"]["number"] is not None else 2.5

        due_cards.append({
            "uuid": row["id"],
            "lemma": lemma,
            "meaning": meaning,
            "plural": plural,
            "present": present,
            "next_review_date": next_review_date,
            "interval": interval,
            "ease": ease
        })
        
    return due_cards

def update_card(uuid, next_date, new_interval, new_ease):
    url = f"https://api.notion.com/v1/pages/{uuid}"
    
    payload = {
        "properties": {
            "next_review_date": {"date": {"start": next_date}},
            "interval": {"number": new_interval},
            "ease_factor": {"number": new_ease}
        }
    }
    
    response = requests.patch(url, json=payload, headers=HEADERS)
    return response.status_code == 200