"""
Unit tests for Step 8 Validation Suite: PK, FK, Enums, Dates, Arithmetic integrity.
"""
from src.generator import SyntheticDataGenerator, DatasetValidator


def test_dataset_validator_all_checks_pass():
    gen = SyntheticDataGenerator(seed=20261022, scale="starter")
    data = gen.generate_all()

    validator = DatasetValidator(data)
    results = validator.validate_all()

    assert results["is_valid"] is True
    assert results["summary"]["failed_checks"] == 0
    assert results["checks"]["PRIMARY_KEY_UNIQUENESS"]["status"] == "PASS"
    assert results["checks"]["FOREIGN_KEY_INTEGRITY"]["status"] == "PASS"
    assert results["checks"]["ALLOWED_ENUMS_VALIDATION"]["status"] == "PASS"
    assert results["checks"]["ARITHMETIC_RECONCILIATION"]["status"] == "PASS"
