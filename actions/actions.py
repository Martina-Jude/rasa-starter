
from typing import Any, Dict, List, Text
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet


class ActionCalculateBudget(Action):

    def name(self) -> Text:
        return "action_calculate_budget"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        income = float(tracker.get_slot("monthly_income"))
        rent = float(tracker.get_slot("rent"))
        insurance = float(tracker.get_slot("insurance"))
        groceries = float(tracker.get_slot("groceries"))

        total_expenses = rent + insurance + groceries
        remaining = round(income - total_expenses, 2)

        dispatcher.utter_message(
            text=(
                f"That means your main expenses are around "
                f"€{total_expenses:,.2f}, leaving you approximately "
                f"€{remaining:,.2f} for other expenses. "
                f"We could divide some of that between social "
                f"activities, unexpected costs, and savings."
            )
        )

        return [SlotSet("remaining_budget", remaining)]


class ActionSuggestBudget(Action):

    def name(self) -> Text:
        return "action_suggest_budget"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        remaining = float(tracker.get_slot("remaining_budget"))

        if remaining <= 0:
            dispatcher.utter_message(
                text=(
                    "It looks like there isn't any money left "
                    "after your main expenses. We can look "
                    "at possible adjustments instead."
                )
            )
            return []

        social = round(remaining * 120 / 270, 2)
        unexpected = round(remaining * 100 / 270, 2)
        savings = round(remaining - social - unexpected, 2)

        dispatcher.utter_message(
            text=(
                f"Sure! With €{remaining:,.2f} left, one option "
                f"could be €{social:,.2f} for social activities, "
                f"€{unexpected:,.2f} for unexpected expenses, "
                f"and €{savings:,.2f} for savings. "
                f"Do you want to adjust these amounts depending "
                f"on what is most important to you?"
            )
        )

        return []


class ActionAdjustBudget(Action):

    def name(self) -> Text:
        return "action_adjust_budget"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        remaining = float(
            tracker.get_slot("remaining_budget") or 0
        )

        priority = (
            tracker.get_slot("budget_priority") or ""
        ).lower()

        if remaining <= 0:
            dispatcher.utter_message(
                text="There isn't any money left to divide."
            )
            return []

        if "sav" in priority:
            savings = round(remaining / 3, 2)
            social = round(remaining / 3, 2)
            unexpected = round(
                remaining - savings - social, 2
            )

            dispatcher.utter_message(
                text=(
                    f"Since you'd like to save more, "
                    f"one option would be €{savings:.2f} "
                    f"for savings, €{social:.2f} for social "
                    f"activities, and €{unexpected:.2f} "
                    f"for unexpected expenses. "
                    f"Would that work for you?"
                )
            )

        else:
            dispatcher.utter_message(
                text=(
                    "We can adjust the amounts based on "
                    "your priorities. Tell me which "
                    "category you'd like to increase."
                )
            )

        return []
