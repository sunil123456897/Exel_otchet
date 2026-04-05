"""Тесты для data_schemas.py — Pydantic модели."""
import pytest
from decimal import Decimal
from core.domain.data_schemas import FinancialRowSchema


class TestFinancialRowSchema:
    """Тесты Pydantic схемы финансовой строки."""

    def test_valid_minimal_row(self):
        row = FinancialRowSchema(
            amount=Decimal('100.00'),
            customer='ООО Заказчик',
        )
        assert row.amount == Decimal('100.00')
        assert row.customer == 'ООО Заказчик'

    def test_valid_full_row(self):
        row = FinancialRowSchema(
            date='01.04.2026',
            amount=Decimal('500.00'),
            income=Decimal('500.00'),
            expense=Decimal('0.00'),
            customer='ООО Клиент',
            contractor='ИП Иванов',
            commission=Decimal('2.50'),
            total=Decimal('500.00'),
            percent_broker=Decimal('0.05'),
            broker1=Decimal('25.00'),
            broker2=Decimal('0.00'),
            filters='доп сф',
        )
        assert row.amount == Decimal('500.00')
        assert row.commission == Decimal('2.50')

    def test_null_values(self):
        row = FinancialRowSchema(
            amount=None,
            customer=None,
        )
        assert row.amount == Decimal('0.00') or row.amount is None

    def test_string_amount_converted(self):
        """Pydantic должен конвертировать строку в Decimal."""
        row = FinancialRowSchema(
            amount='100.50',
            customer='Test',
        )
        assert row.amount == Decimal('100.50')

    def test_model_dump(self):
        row = FinancialRowSchema(
            amount=Decimal('200.00'),
            customer='Test',
            contractor='Contractor',
        )
        data = row.model_dump()
        assert 'amount' in data
        assert data['customer'] == 'Test'
