import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.mandates.adapters.mock_adapter import MockAdapter


def test_catalog_not_empty():
    adapter = MockAdapter()
    catalog = adapter.get_catalog()
    assert len(catalog) > 0


def test_catalog_items_have_required_fields():
    catalog = MockAdapter().get_catalog()
    for item in catalog:
        assert "name" in item
        assert "price" in item
        assert "category" in item


def test_margin_policy_exists():
    policy = MockAdapter().get_margin_policy()
    assert len(policy) > 10
