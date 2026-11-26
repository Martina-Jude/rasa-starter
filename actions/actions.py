
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

class ActionApplyBudgetEdit(Action):
    def name(self):
        return "action_apply_budget_edit"

    def run(self, dispatcher, tracker, domain):
        field = tracker.get_slot("edit_budget_field")
        amount = tracker.get_slot("edit_budget_amount")
        slot_name = "monthly_income" if field == "income" else field

        fields = ("monthly_income", "rent", "insurance", "groceries")
        amounts = {name: tracker.get_slot(name) for name in fields}
        amounts[slot_name] = amount

        message = f"I updated your monthly {field} to {euros(int(Decimal(amount) * 100))}."
        remaining = 0

        if all(value is not None for value in amounts.values()):
            cents = {name: int(Decimal(value) * 100) for name, value in amounts.items()}
            remaining = cents["monthly_income"] - sum(
                cents[name] for name in ("rent", "insurance", "groceries")
            )
            if remaining >= 0:
                message += f" You now have {euros(remaining)} left each month."
            else:
                message += f" Your expenses now exceed your income by {euros(-remaining)}."

        dispatcher.utter_message(text=message)
        return [
            SlotSet(slot_name, amount),
            SlotSet("remaining_budget_cents", remaining),
        ]
