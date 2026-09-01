from datetime import datetime, timezone, timedelta

def calculate_sm2(grade, current_interval, current_ease):
    """
    grade: 1 (Again), 2 (Hard), 3 (Good), 4 (Easy)
    """
    if grade == 1:
        new_interval = 0
        new_ease = max(1.3, current_ease - 0.2) # lowers ease_rating
    else:
        if current_interval == 0:
            # First time graduating a card
            new_interval = 1 if grade == 2 else (3 if grade == 3 else 4)
            new_ease = current_ease
        else:
            if grade == 2:
                new_interval = current_interval * 1.2
                new_ease = max(1.3, current_ease - 0.15)
            elif grade == 3:
                new_interval = current_interval * current_ease
                new_ease = current_ease
            elif grade == 4:
                new_interval = current_interval * current_ease * 1.3
                new_ease = current_ease + 0.15

    new_interval = round(new_interval)
    next_date = (datetime.now(timezone.utc) + timedelta(days=new_interval)).strftime("%Y-%m-%d")
    
    return new_interval, round(new_ease, 2), next_date