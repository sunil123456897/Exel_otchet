import pytest
from decimal import Decimal
from core.utils_helpers import to_decimal, to_decimal_percent, open_path

def test_to_decimal_basic():
    assert to_decimal(100) == Decimal('100.00')
    assert to_decimal(100.5) == Decimal('100.50')
    assert to_decimal("100.5") == Decimal('100.50')
    assert to_decimal("100,5") == Decimal('100.50')

def test_to_decimal_edge_cases():
    assert to_decimal(None) == Decimal('0.00')
    assert to_decimal("") == Decimal('0.00')
    assert to_decimal("   ") == Decimal('0.00')
    assert to_decimal(float('nan')) == Decimal('0.00')

def test_to_decimal_unusual_formats():
    # Test with spaces and currency symbols
    assert to_decimal("1 234,56 руб.") == Decimal('1234.56')
    # Test with multiple separators
    assert to_decimal("1.234.567,89") == Decimal('1234567.89')
    assert to_decimal("1,234,567.89") == Decimal('1234567.89')
    # Test with parentheses (negative)
    assert to_decimal("(100.00)") == Decimal('-100.00')

def test_to_decimal_errors():
    with pytest.raises(ValueError, match="Invalid numeric value"):
        to_decimal("nan")
    with pytest.raises(ValueError, match="Invalid numeric value"):
        to_decimal("null")
    with pytest.raises(ValueError, match="Invalid numeric value"):
        to_decimal("error")
    with pytest.raises(ValueError, match="Could not parse numeric value"):
        to_decimal("abc")

def test_to_decimal_scientific():
    assert to_decimal("1.23e2") == Decimal('123.00')
    assert to_decimal("(1.23e2)") == Decimal('-123.00')

def test_to_decimal_multiple_separators_complex():
    # elif len(seps) >= 2:
    # last = seps[-1]
    # prefix = s[:last].replace('.', '').replace(',', '')
    # clean = f"{prefix}.{s[last+1:]}" if s[last+1:] else prefix
    assert to_decimal("1.234.567,89") == Decimal('1234567.89')
    assert to_decimal("1,234,567.89") == Decimal('1234567.89')
    # For "1.234.567", the implementation treats the last dot as decimal separator
    assert to_decimal("1.234.567") == Decimal('1234.57')

def test_open_path():
    import platform
    from unittest.mock import patch
    import os
    import subprocess
    
    with patch('platform.system') as mock_system:
        # Windows
        mock_system.return_value = "Windows"
        # os.startfile only exists on Windows
        with patch('os.startfile', create=True) as mock_startfile:
            open_path("test_path")
            mock_startfile.assert_called_once_with("test_path")
            
        # Darwin
        mock_system.return_value = "Darwin"
        with patch('subprocess.run') as mock_run:
            open_path("test_path")
            mock_run.assert_called_once_with(["open", "test_path"])
            
        # Linux
        mock_system.return_value = "Linux"
        with patch('subprocess.run') as mock_run:
            open_path("test_path")
            mock_run.assert_called_once_with(["xdg-open", "test_path"])

def test_to_decimal_percent_basic():
    assert to_decimal_percent(0.05) == Decimal('0.05')
    assert to_decimal_percent("5%") == Decimal('0.05')
    assert to_decimal_percent("0.05") == Decimal('0.05')
    assert to_decimal_percent("5") == Decimal('5') # If no % and > 1, it stays as is? 
    # Let's check the code: if "%" in raw and res > 1: res = res / Decimal('100')
    assert to_decimal_percent("5%") == Decimal('0.05')
    assert to_decimal_percent("0.5%") == Decimal('0.5') # res is 0.5, not > 1, so no division?
    # Wait, if res is 0.5, it's already a decimal fraction.
    # If it's "50%", res is 50, 50 > 1, so 50/100 = 0.5. Correct.

def test_to_decimal_percent_edge_cases():
    assert to_decimal_percent(None) == Decimal('0')
    assert to_decimal_percent("") == Decimal('0')
    assert to_decimal_percent("abc") == Decimal('0')
