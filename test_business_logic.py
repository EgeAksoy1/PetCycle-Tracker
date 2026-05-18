import pytest
from datetime import date, timedelta
from app import (
    calculate_food_remaining,
    calculate_next_due_date,
    calculate_days_left,
    calculate_fed,
)

# ─── calculate_food_remaining ─────────────────────────────────────────────────

class TestCalculateFoodRemaining:

    def test_same_day_no_consumption(self):
        """Aynı gün stok açıldıysa tüketim sıfır olmalı."""
        today = date.today()
        result = calculate_food_remaining(5000, 250, today.strftime('%Y-%m-%d'), today)
        assert result['calculated_remaining_amount'] == 5000
        assert result['food_remaining_days'] == 20

    def test_one_day_passed(self):
        """1 gün geçmişse bir günlük mama düşmeli."""
        yesterday = date.today() - timedelta(days=1)
        result = calculate_food_remaining(5000, 250, yesterday.strftime('%Y-%m-%d'), date.today())
        assert result['calculated_remaining_amount'] == 4750
        assert result['food_remaining_days'] == 19

    def test_stock_cannot_go_negative(self):
        """Stok negatife düşmemeli, minimum 0 olmalı."""
        old_date = date.today() - timedelta(days=100)
        result = calculate_food_remaining(500, 250, old_date.strftime('%Y-%m-%d'), date.today())
        assert result['calculated_remaining_amount'] == 0
        assert result['food_remaining_days'] == 0

    def test_zero_daily_gram_returns_zero_days(self):
        """Günlük miktar 0 ise sıfıra bölme hatası olmamalı."""
        today = date.today()
        result = calculate_food_remaining(5000, 0, today.strftime('%Y-%m-%d'), today)
        assert result['food_remaining_days'] == 0

    def test_future_date_treated_as_zero_days(self):
        """last_action_date gelecekte ise days_passed 0 olmalı."""
        future = date.today() + timedelta(days=5)
        result = calculate_food_remaining(5000, 250, future.strftime('%Y-%m-%d'), date.today())
        assert result['calculated_remaining_amount'] == 5000


# ─── calculate_next_due_date ──────────────────────────────────────────────────

class TestCalculateNextDueDate:

    def test_basic_calculation(self):
        """30 gün aralıkla sonraki tarih doğru hesaplanmalı."""
        result = calculate_next_due_date('2026-05-01', 30)
        assert result == '2026-05-31'

    def test_none_interval_returns_none(self):
        """interval_days yoksa None dönmeli."""
        result = calculate_next_due_date('2026-05-01', None)
        assert result is None

    def test_none_last_action_uses_today(self):
        """last_action_date yoksa bugünden hesaplanmalı."""
        today = date.today()
        expected = (today + timedelta(days=7)).strftime('%Y-%m-%d')
        result = calculate_next_due_date(None, 7)
        assert result == expected

    def test_one_day_interval(self):
        result = calculate_next_due_date('2026-01-01', 1)
        assert result == '2026-01-02'

    def test_large_interval(self):
        result = calculate_next_due_date('2026-01-01', 365)
        assert result == '2027-01-01'


# ─── calculate_days_left ──────────────────────────────────────────────────────

class TestCalculateDaysLeft:

    def test_future_date(self):
        """Gelecekteki tarih pozitif gün dönmeli."""
        future = (date.today() + timedelta(days=5)).strftime('%Y-%m-%d')
        assert calculate_days_left(future, date.today()) == 5

    def test_past_date(self):
        """Geçmişteki tarih negatif gün dönmeli."""
        past = (date.today() - timedelta(days=3)).strftime('%Y-%m-%d')
        assert calculate_days_left(past, date.today()) == -3

    def test_today(self):
        """Bugünün tarihi 0 dönmeli."""
        today = date.today().strftime('%Y-%m-%d')
        assert calculate_days_left(today, date.today()) == 0

    def test_none_returns_none(self):
        """next_due_date yoksa None dönmeli."""
        assert calculate_days_left(None) is None


# ─── calculate_fed ────────────────────────────────────────────────────────────

class TestCalculateFed:

    def test_normal_deduction(self):
        """Bir günlük mama stoktan düşmeli."""
        assert calculate_fed(5000, 250) == 4750

    def test_cannot_go_negative(self):
        """Stok negatife düşmemeli."""
        assert calculate_fed(100, 250) == 0

    def test_exact_deduction(self):
        """Tam stok kadar düşünce 0 olmalı."""
        assert calculate_fed(250, 250) == 0

    def test_none_total_treated_as_zero(self):
        """total_amount None ise 0 kabul edilmeli."""
        assert calculate_fed(None, 250) == 0