"""Pure-function tests for owner-mailing-address-vs-property-address
comparison -- no network, per this project's two-layer testing standard.
"""
from __future__ import annotations

from extscorer.normalize.address import (
    format_owner_mailing_address,
    is_owner_address_mismatch,
    normalize_street_address,
    split_owner_mailing_address,
)


def test_normalize_street_address_abbreviates_common_street_types() -> None:
    assert normalize_street_address("20 MAPLE DRIVE") == "20 MAPLE DR"
    assert normalize_street_address("20 MAPLE DR") == "20 MAPLE DR"


def test_normalize_street_address_strips_punctuation_and_whitespace() -> None:
    assert normalize_street_address("  20 Maple Dr.  ") == "20 MAPLE DR"


def test_normalize_street_address_none_and_blank() -> None:
    assert normalize_street_address(None) is None
    assert normalize_street_address("") is None
    assert normalize_street_address("   ") is None


def test_split_owner_mailing_address_real_vgsi_shape() -> None:
    # Real confirmed VGSI shape (Canterbury pid 1329): the name lives in a
    # separate span, so `raw_lines` here is address-only.
    lines = ["20 MAPLE DR", "CANTERBURY, CT 06331"]
    street, city_state_zip = split_owner_mailing_address(lines)
    assert street == "20 MAPLE DR"
    assert city_state_zip == "CANTERBURY, CT 06331"


def test_split_owner_mailing_address_drops_trailing_blank_line() -> None:
    # Real confirmed PRC shape ends with a trailing <br>, i.e. a blank
    # split segment -- must not be treated as a real third field.
    lines = ["32 OAK ST", "KILLINGLY, CT 06239", ""]
    street, city_state_zip = split_owner_mailing_address(lines)
    assert street == "32 OAK ST"
    assert city_state_zip == "KILLINGLY, CT 06239"


def test_split_owner_mailing_address_empty_input() -> None:
    assert split_owner_mailing_address([]) == (None, None)


def test_format_owner_mailing_address_joins_with_comma() -> None:
    assert format_owner_mailing_address("20 MAPLE DR", "CANTERBURY, CT 06331") == "20 MAPLE DR, CANTERBURY, CT 06331"


def test_format_owner_mailing_address_handles_missing_parts() -> None:
    assert format_owner_mailing_address(None, None) is None
    assert format_owner_mailing_address("20 MAPLE DR", None) == "20 MAPLE DR"


def test_is_owner_address_mismatch_true_for_real_absentee_case() -> None:
    # Owner mails to a different street than the property's own address --
    # the real absentee-owner signal the client asked for.
    assert is_owner_address_mismatch("32 OAK ST", "14 MAIN ST") is True


def test_is_owner_address_mismatch_false_when_owner_lives_there() -> None:
    assert is_owner_address_mismatch("20 MAPLE DR", "20 MAPLE DRIVE") is False


def test_is_owner_address_mismatch_false_when_either_side_missing() -> None:
    # Unknown must not be treated as confirmed mismatch.
    assert is_owner_address_mismatch(None, "14 MAIN ST") is False
    assert is_owner_address_mismatch("32 OAK ST", None) is False
    assert is_owner_address_mismatch(None, None) is False
