"""Pure-function tests for owner-mailing-address-vs-property-address
comparison -- no network, per this project's two-layer testing standard.
"""
from __future__ import annotations

import pytest

from extscorer.normalize.address import (
    format_owner_mailing_address,
    is_owner_address_mismatch,
    normalize_street_address,
    parse_owner_mailing_block,
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

# --- care-of / attention and extra name lines. The blocks below are INVENTED (names, streets, towns)
# --- but have exactly the shapes seen on real propertyrecordcards.com and VGSI cards.

_CARE_OF_BLOCKS = [
    # (raw lines, care_of, street, city_state_zip)
    (["C/O PAT EXAMPLE FIDUCIARY", "190 SAMPLE RD", "TESTVILLE, CT 06000", ""], "C/O PAT EXAMPLE FIDUCIARY", "190 SAMPLE RD", "TESTVILLE, CT 06000"),
    (["C/O SAM SPECIMEN", "22 MODEL CIRCLE", "DEMOTOWN, CT 06001", ""], "C/O SAM SPECIMEN", "22 MODEL CIRCLE", "DEMOTOWN, CT 06001"),
    (["C/O LEE PLACEHOLDER", "PO BOX 999", "TESTVILLE, CT 06000", ""], "C/O LEE PLACEHOLDER", "PO BOX 999", "TESTVILLE, CT 06000"),
    (["C/O ALEX FICTION", "5599 SHORE DRIVE", "SAMPLE BEACH, FL 33000", ""], "C/O ALEX FICTION", "5599 SHORE DRIVE", "SAMPLE BEACH, FL 33000"),
    (["C/O CASEY DEMO", "46 SAMPLE ST", "EXAMPLEBURG, MA 01000"], "C/O CASEY DEMO", "46 SAMPLE ST", "EXAMPLEBURG, MA 01000"),
    (["ATTN: TAX DEPARTMENT", "PO BOX 999", "ANYCITY, TX 75000"], "ATTN: TAX DEPARTMENT", "PO BOX 999", "ANYCITY, TX 75000"),
    # No street at all: a care-of line straight into the city line.
    (["C/O TOWN HALL", "TESTVILLE, CT 06000"], "C/O TOWN HALL", None, "TESTVILLE, CT 06000"),
]


@pytest.mark.parametrize("lines,care_of,street,city", _CARE_OF_BLOCKS)
def test_care_of_blocks_keep_the_street_apart_from_the_care_of_name(lines, care_of, street, city) -> None:
    block = parse_owner_mailing_block(lines)
    assert (block.care_of, block.street, block.city_state_zip) == (care_of, street, city)
    assert split_owner_mailing_address(lines) == (street, city)


def test_a_care_of_line_is_never_taken_as_the_street() -> None:
    street, _ = split_owner_mailing_address(["C/O PAT EXAMPLE", "PO BOX 999", "TESTVILLE, CT 06000"])
    assert street == "PO BOX 999"


def test_absentee_flag_follows_the_real_street_not_the_care_of_line() -> None:
    # The owner's mailing street IS the property's street, with a care-of line in front. The old
    # splitter took "C/O ..." as the street and called this owner absentee.
    street, _ = split_owner_mailing_address(["C/O PROPERTY MGR", "12 MAIN ST", "TOWN, CT 06000"])
    assert is_owner_address_mismatch("12 MAIN ST", street) is False
    # A genuinely different mailing street is still absentee, care-of line or not.
    street, _ = split_owner_mailing_address(["C/O PAT EXAMPLE FIDUCIARY", "190 SAMPLE RD", "TESTVILLE, CT 06000"])
    assert is_owner_address_mismatch("111 OTHER RD", street) is True


def test_no_street_means_no_absentee_claim() -> None:
    street, _ = split_owner_mailing_address(["C/O TOWN HALL", "TESTVILLE, CT 06000"])
    assert street is None
    assert is_owner_address_mismatch("HANOVER RD", street) is False  # absence of data is not evidence


def test_a_suite_line_after_the_street_does_not_displace_it() -> None:
    block = parse_owner_mailing_block(["C/O ACME COMPANY INC", "650 SAMPLE ST", "SUITE 1", "EXAMPLEBURG, MA 01000"])
    assert block.street == "650 SAMPLE ST"


def test_a_block_with_no_recognisable_city_line_falls_back_to_street_then_next_line() -> None:
    assert split_owner_mailing_address(["12 MAIN ST", "SOMEWHERE"]) == ("12 MAIN ST", "SOMEWHERE")


# A second name line (co-owner, trust, "% NAME") before the street: the old splitter read it as the
# street and flagged a resident owner as absentee.
_SECOND_NAME_BLOCKS = [
    (["PAT EXAMPLE", "85 SAMPLE RD", "TESTVILLE, CT 06000", ""], "85 SAMPLE RD"),
    (["% SAM SPECIMEN", "EXAMPLE FAMILY TRUST", "13 MODEL LN", "DEMOTOWN, CT 06001"], "13 MODEL LN"),
    (["EXAMPLE INC", "C/O MINISTRIES", "574 SAMPLE CENTER RD", "TESTVILLE, CT 06000", ""], "574 SAMPLE CENTER RD"),
    # a trust date on its own line must not be mistaken for the street
    (["01/01/2000", "32 MODEL DR", "TESTVILLE, CT 06000"], "32 MODEL DR"),
    (["10 SAMPLE ST", "APT 1", "EXAMPLEBURG, MA 01000"], "10 SAMPLE ST"),
]


@pytest.mark.parametrize("lines,street", _SECOND_NAME_BLOCKS)
def test_a_second_name_line_is_never_taken_as_the_street(lines, street) -> None:
    assert parse_owner_mailing_block(lines).street == street


def test_resident_owner_with_a_second_name_line_is_not_absentee() -> None:
    street, _ = split_owner_mailing_address(["% CASEY DEMO", "11 SAMPLE LN", "TESTVILLE, CT 06000"])
    assert is_owner_address_mismatch("11 SAMPLE LN", street) is False

