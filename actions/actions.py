import re
from decimal import Decimal

from rasa_sdk import Action
from rasa_sdk.events import SlotSet


BUDGET_FIELDS = ("monthly_income", "rent", "insurance", "groceries")
CATEGORIES = ("social_activities", "unexpected_expenses", "savings")
DEFAULT_WEIGHTS = dict(zip(CATEGORIES, (40, 35, 25)))
AMOUNT_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]{1,2})?")


def euros(cents):
    whole, fraction = divmod(abs(cents), 100)
    sign = "-" if cents < 0 else ""
    return f"{sign}€{whole:,}.{fraction:02d}"


def to_cents(value):
    return int(Decimal(str(value)) * 100)


def valid_amount(value):
    return isinstance(value, str) and AMOUNT_PATTERN.fullmatch(value) is not None


def get_budget_amounts(tracker):
    return {field: tracker.get_slot(field) for field in BUDGET_FIELDS}


def budget_totals(amounts):
    if not all(valid_amount(value) for value in amounts.values()):
        return None

    expenses = sum(to_cents(amounts[field]) for field in BUDGET_FIELDS[1:])
    remaining = to_cents(amounts["monthly_income"]) - expenses
    return expenses, remaining


def split_by_weight(total, weights):
    weight_total = sum(weights.values())
    if weight_total == 0:
        weights = dict.fromkeys(weights, 1)
        weight_total = len(weights)

    split = {
        category: total * weight // weight_total
        for category, weight in weights.items()
    }
    last_category = next(reversed(split))
    split[last_category] += total - sum(split.values())
    return split


def split_events(split):
    return [SlotSet(category, split[category] / 100) for category in CATEGORIES]


def adjust_allocations(total, current, request):
    fixed = {}
    increase = []

    for item in request.split("|"):
        category, _, value = item.partition("=")
        category, value = category.strip(), value.strip()

        if category not in CATEGORIES or category in fixed or category in increase:
            raise ValueError("Please name each category you want to change once.")

        if value == "more":
            increase.append(category)
        elif valid_amount(value):
            fixed[category] = to_cents(value)
        else:
            raise ValueError("Give an amount in euros or ask for more in a category.")

    flexible = [
        category for category in CATEGORIES
        if category not in fixed and category not in increase
    ]
    available = total - sum(fixed.values()) - sum(current[key] for key in increase)

    if available < len(increase):
        raise ValueError("There isn't enough money left for those changes. Try a smaller amount.")

    updated = fixed.copy()

    if increase:
        extra = available
        if flexible:
            extra = min(extra, max(1, total // 10) * len(increase))

        increment, leftover = divmod(extra, len(increase))
        for index, category in enumerate(increase):
            updated[category] = current[category] + increment + (index < leftover)
        available -= extra

    if flexible:
        updated.update(
            split_by_weight(available, {category: current[category] for category in flexible})
        )
    elif available:
        raise ValueError(f"The three amounts need to add up to {euros(total)}.")

    return updated


class ActionCalculateBudget(Action):
    def name(self):
        return "action_calculate_budget"

    def run(self, dispatcher, tracker, domain):
        totals = budget_totals(get_budget_amounts(tracker))
        if totals is None:
            dispatcher.utter_message(
                text="I need a valid amount for each item to calculate your budget."
            )
            return [
                SlotSet("total_expenses", None),
                SlotSet("remaining_budget", None),
            ]

        expenses, remaining = totals

        if remaining > 0:
            result = f"That leaves {euros(remaining)} for the rest of the month."
        elif remaining == 0:
            result = "These expenses use all of your monthly income."
        else:
            result = f"That's {euros(-remaining)} more than your monthly income."

        dispatcher.utter_message(
            text=f"Your rent, insurance, and groceries add up to {euros(expenses)}. {result}"
        )

        return [
            SlotSet("total_expenses", expenses / 100),
            SlotSet("remaining_budget", remaining / 100),
            SlotSet("budget_saved", False),
            *[SlotSet(category, None) for category in CATEGORIES],
        ]


class ActionApplyBudgetEdit(Action):
    def name(self):
        return "action_apply_budget_edit"

    def run(self, dispatcher, tracker, domain):
        field = tracker.get_slot("edit_budget_field")
        amount = tracker.get_slot("edit_budget_amount")
        slot_name = "monthly_income" if field == "income" else field

        if slot_name not in BUDGET_FIELDS or not valid_amount(amount):
            dispatcher.utter_message(response="utter_incorrect_amount")
            return []

        amounts = get_budget_amounts(tracker)
        amounts[slot_name] = amount

        message = f"I updated your monthly {field} to {euros(to_cents(amount))}."
        events = [
            SlotSet(slot_name, amount),
            SlotSet("edit_budget_field", None),
            SlotSet("edit_budget_amount", None),
        ]

        totals = budget_totals(amounts)
        if totals is not None:
            expenses, remaining = totals
            events.extend([
                SlotSet("total_expenses", expenses / 100),
                SlotSet("remaining_budget", remaining / 100),
            ])

            if remaining >= 0:
                message += f" You now have {euros(remaining)} left each month."
            else:
                message += f" Your expenses now exceed your income by {euros(-remaining)}."

        dispatcher.utter_message(text=message)
        return events


class ActionSuggestBudget(Action):
    def name(self):
        return "action_suggest_budget"

    def run(self, dispatcher, tracker, domain):
        remaining = tracker.get_slot("remaining_budget")
        if remaining is None or remaining <= 0:
            return []

        return split_events(split_by_weight(to_cents(remaining), DEFAULT_WEIGHTS))


class ActionAdjustBudget(Action):
    def name(self):
        return "action_adjust_budget"

    def run(self, dispatcher, tracker, domain):
        request = tracker.get_slot("budget_adjustment_request")
        remaining = tracker.get_slot("remaining_budget")

        if remaining is None or remaining <= 0:
            dispatcher.utter_message(text="There's no money left to divide.")
            return []

        if not request or request == "invalid":
            dispatcher.utter_message(
                text="Which categories should change, and by how much?"
            )
            return []

        total = to_cents(remaining)
        current = {
            category: to_cents(tracker.get_slot(category) or 0)
            for category in CATEGORIES
        }

        if sum(current.values()) != total:
            current = split_by_weight(total, DEFAULT_WEIGHTS)

        preview = request == "suggest"
        if preview:
            category = min(CATEGORIES, key=current.get)
            request = f"{category}=more"

        try:
            updated = adjust_allocations(total, current, request)
        except ValueError as error:
            dispatcher.utter_message(text=str(error))
            return []

        split = ", ".join(
            f"{euros(updated[key])} for {key.replace('_', ' ')}"
            for key in CATEGORIES
        )

        if preview:
            category_name = category.replace("_", " ")
            dispatcher.utter_message(
                text=f"One option is {split}. Say 'more for {category_name}' to apply it."
            )
            return []

        dispatcher.utter_message(text=f"Here's your updated split: {split}.")
        return split_events(updated)


class ActionSaveBudget(Action):
    def name(self):
        return "action_save_budget"

    def run(self, dispatcher, tracker, domain):
        # The flow calls this action after the user confirms.
        return [SlotSet("budget_saved", True)]