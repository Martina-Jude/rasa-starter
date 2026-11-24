
from typing import Any, Dict, List, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

import re
from decimal import Decimal


def euros(cents):
    whole, fraction = divmod(cents, 100)
    return f"€{whole:,}.{fraction:02d}"


class ActionCalculateBudget(Action):
    def name(self):
        return "action_calculate_budget"

    def run(self, dispatcher, tracker, domain):
        fields = ("monthly_income", "rent", "insurance", "groceries")
        amounts = {}

        for field in fields:
            value = tracker.get_slot(field)

            if not isinstance(value, str) or not re.fullmatch(
                r"[0-9]+(?:\.[0-9]{1,2})?", value
            ):
                dispatcher.utter_message(
                    text="I need a valid amount for each item to calculate your budget."
                )
                return []

            amounts[field] = int(Decimal(value) * 100)

        expenses = amounts["rent"] + amounts["insurance"] + amounts["groceries"]
        remaining = amounts["monthly_income"] - expenses

        if remaining > 0:
            result = f"That leaves {euros(remaining)} for the rest of the month."
        elif remaining == 0:
            result = "These expenses use all of your monthly income."
        else:
            result = f"That's {euros(-remaining)} more than your monthly income."

        dispatcher.utter_message(
            text=f"Your rent, insurance, and groceries add up to {euros(expenses)}. {result}"
        )
        return []


