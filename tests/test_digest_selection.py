from __future__ import annotations

from extscorer.digest.selection import select_unsent_leads


class _FakeLead:
    def __init__(self, parcel_id: str) -> None:
        self.parcel_id = parcel_id


def test_selects_top_n_leads_in_ranked_order() -> None:
    pairs = [
        (_FakeLead("A"), {"id": "row-a"}),
        (_FakeLead("B"), {"id": "row-b"}),
        (_FakeLead("C"), {"id": "row-c"}),
    ]
    selected = select_unsent_leads(pairs, already_sent_parcel_row_ids=set(), limit=2)
    assert [p["id"] for _, p in selected] == ["row-a", "row-b"]


def test_skips_already_sent_parcels() -> None:
    pairs = [
        (_FakeLead("A"), {"id": "row-a"}),
        (_FakeLead("B"), {"id": "row-b"}),
        (_FakeLead("C"), {"id": "row-c"}),
    ]
    selected = select_unsent_leads(pairs, already_sent_parcel_row_ids={"row-a"}, limit=2)
    assert [p["id"] for _, p in selected] == ["row-b", "row-c"]


def test_returns_fewer_than_limit_if_not_enough_unsent_leads_remain() -> None:
    pairs = [(_FakeLead("A"), {"id": "row-a"}), (_FakeLead("B"), {"id": "row-b"})]
    selected = select_unsent_leads(pairs, already_sent_parcel_row_ids={"row-a"}, limit=10)
    assert len(selected) == 1


def test_returns_empty_when_everything_already_sent() -> None:
    pairs = [(_FakeLead("A"), {"id": "row-a"})]
    selected = select_unsent_leads(pairs, already_sent_parcel_row_ids={"row-a"}, limit=10)
    assert selected == []
