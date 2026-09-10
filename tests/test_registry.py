from typing import Any

import pytest

from extscorer.normalize.schema import ParcelLeadRecord
from extscorer.sources import registry
from extscorer.sources.base import LeadDataSource


class _FakeSource(LeadDataSource):
    def fetch(self) -> list[dict[str, Any]]:
        return [{"town": "Canterbury", "county": "Windham", "address": "1 Fake St", "parcel_id": "1"}]

    def parse(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw

    def normalize(self, raw_record: dict[str, Any]) -> ParcelLeadRecord:
        return ParcelLeadRecord(client_id=self.client_id, raw_data=raw_record, **raw_record)


@pytest.fixture(autouse=True)
def _clean_registry():
    registry._clear_registry_for_tests()
    yield
    registry._clear_registry_for_tests()


def test_register_source_makes_it_resolvable_by_slug() -> None:
    registry.register_source("test-slug")(_FakeSource)
    assert registry.get_source_class("test-slug") is _FakeSource
    assert "test-slug" in registry.registered_source_slugs()


def test_get_source_class_raises_for_unregistered_slug() -> None:
    with pytest.raises(KeyError):
        registry.get_source_class("nonexistent-slug")


def test_register_source_rejects_conflicting_duplicate_slug() -> None:
    registry.register_source("dup-slug")(_FakeSource)

    class _OtherSource(_FakeSource):
        pass

    with pytest.raises(ValueError):
        registry.register_source("dup-slug")(_OtherSource)


def test_register_source_allows_reregistering_the_same_class() -> None:
    registry.register_source("same-class-slug")(_FakeSource)
    # Re-decorating the identical class (e.g. module reimported) should
    # not raise -- only a genuine conflicting registration should.
    registry.register_source("same-class-slug")(_FakeSource)
