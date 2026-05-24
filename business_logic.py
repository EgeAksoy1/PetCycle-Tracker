from datetime import date, datetime, timedelta

def calculate_food_remaining(total_amount, daily_food_gram, last_action_date_str, today=None):
    if today is None:
        today = date.today()
    action_date = datetime.strptime(last_action_date_str[:10], '%Y-%m-%d').date()
    days_passed = max((today - action_date).days, 0)
    consumed = days_passed * daily_food_gram
    remaining_amount = max(total_amount - consumed, 0)
    remaining_days = remaining_amount // daily_food_gram if daily_food_gram > 0 else 0
    return {
        'calculated_remaining_amount': remaining_amount,
        'food_remaining_days': remaining_days
    }

def calculate_next_due_date(last_action_date_str, interval_days):
    if not interval_days:
        return None
    if last_action_date_str:
        base_date = datetime.strptime(last_action_date_str[:10], '%Y-%m-%d').date()
    else:
        base_date = date.today()
    return (base_date + timedelta(days=int(interval_days))).strftime('%Y-%m-%d')

def calculate_days_left(next_due_date_str, today=None):
    if today is None:
        today = date.today()
    if not next_due_date_str:
        return None
    target = datetime.strptime(next_due_date_str[:10], '%Y-%m-%d').date()
    return (target - today).days

def calculate_fed(total_amount, daily_food_gram):
    return max((total_amount or 0) - daily_food_gram, 0)