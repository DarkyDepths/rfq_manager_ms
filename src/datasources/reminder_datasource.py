"""
Reminder datasource — database queries for the `reminder` table.

Also handles reminder_rule queries.

Methods:
- create(data)                     — INSERT new reminder
- list(filters)                    — SELECT with user, status, rfq_id filters
- get_stats()                      — aggregate KPIs (open, overdue, due_this_week, with_active)
- list_rules()                     — SELECT all reminder rules
- update_rule(rule_id, data)       — partial UPDATE rule (is_active toggle)
"""

from __future__ import annotations

from datetime import date, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.reminder import Reminder, ReminderRule


class ReminderDatasource:

    def __init__(self, session: Session):
        self.session = session

    # ── Reminders ─────────────────────────────────────

    def create(self, data: dict) -> Reminder:
        reminder = Reminder(**data)
        self.session.add(reminder)
        self.session.flush()
        self.session.refresh(reminder)
        return reminder

    def get_by_id(self, reminder_id) -> Reminder | None:
        return self.session.query(Reminder).filter(Reminder.id == reminder_id).first()

    def list(self, user: str = None, status: str = None, rfq_id=None) -> list[Reminder]:
        today = date.today()
        query = self.session.query(Reminder)
        if user:
            query = query.filter(Reminder.assigned_to == user)
        if status:
            normalized_status = status.strip().lower()
            if normalized_status == "resolved":
                query = query.filter(Reminder.status == "resolved")
            elif normalized_status == "overdue":
                query = query.filter(Reminder.status != "resolved", Reminder.due_date < today)
            elif normalized_status == "open":
                query = query.filter(Reminder.status != "resolved", Reminder.due_date >= today)
            else:
                query = query.filter(Reminder.status == normalized_status)
        if rfq_id:
            query = query.filter(Reminder.rfq_id == rfq_id)
        return query.order_by(Reminder.due_date.asc()).all()

    def get_stats(self) -> dict:
        today = date.today()
        week_end = today + timedelta(days=7)
        active_filter = Reminder.status != "resolved"

        open_count = (
            self.session.query(func.count(Reminder.id))
            .filter(active_filter, Reminder.due_date >= today)
            .scalar()
        )
        overdue_count = self.session.query(func.count(Reminder.id)).filter(
            active_filter,
            Reminder.due_date < today,
        ).scalar()
        due_this_week = self.session.query(func.count(Reminder.id)).filter(
            active_filter,
            Reminder.due_date >= today,
            Reminder.due_date <= week_end,
        ).scalar()
        with_active = self.session.query(func.count(func.distinct(Reminder.rfq_id))).filter(
            active_filter,
        ).scalar()

        return {
            "open_tasks": open_count or 0,
            "overdue_tasks": overdue_count or 0,
            "due_this_week": due_this_week or 0,
            "with_active_reminders": with_active or 0,
        }

    # ── Rules ─────────────────────────────────────────

    def list_rules(self) -> list[ReminderRule]:
        return self.session.query(ReminderRule).order_by(ReminderRule.name).all()

    def get_rule_by_id(self, rule_id) -> ReminderRule | None:
        return self.session.query(ReminderRule).filter(ReminderRule.id == rule_id).first()

    def update_rule(self, rule: ReminderRule, data: dict) -> ReminderRule:
        for key, value in data.items():
            if hasattr(rule, key):
                setattr(rule, key, value)
        self.session.flush()
        self.session.refresh(rule)
        return rule

    def update(self, reminder: Reminder, data: dict) -> Reminder:
        for key, value in data.items():
            if hasattr(reminder, key):
                setattr(reminder, key, value)
        self.session.flush()
        self.session.refresh(reminder)
        return reminder
