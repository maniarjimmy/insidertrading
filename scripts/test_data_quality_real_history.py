import sys, os
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_quality import validate_candle
from corporate_actions import load_cached_actions, save_cached_actions

# Inject CANBK 2024-05-15 split action into cache
actions = load_cached_actions()
actions.append({
    "symbol": "CANBK",
    "ex_date": "2024-05-15",
    "action_type": "SPLIT",
    "ratio": 5.0,
    "purpose": "Stock Split from Rs. 10/- to Rs. 2/-"
})
save_cached_actions(actions)

candle_split = {
    "symbol": "CANBK",
    "open": 22.5, "high": 23.8, "low": 22.0, "close": 23.5,
    "volume": 58000000,
    "price_change": -79.2
}
valid, reason = validate_candle(candle_split, date(2024, 5, 15))
print(f"Case 1 [CANBK Split Ex-Date (with Corp Action in cache)]:")
print(f"  Valid: {valid} | Reason: {reason}")
