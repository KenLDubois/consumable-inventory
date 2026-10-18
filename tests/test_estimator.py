from datetime import UTC, datetime, timedelta

import pytest

from consumable_inventory.estimator import (
    Change,
    Reading,
    container_quantity,
    estimate,
    list_line,
    usage_rate,
)

T0 = datetime(2026, 10, 1, 9, tzinfo=UTC)
HOME, GARAGE = 1, 2


def day(n: float) -> datetime:
    return T0 + timedelta(days=n)


def test_no_readings_means_unknown_stock():
    est = estimate([], [], now=day(0))

    assert est.on_hand is None
    assert est.usage_per_day is None


def test_opened_container_counts_as_half():
    assert container_quantity(unopened=1, opened=1) == 1.5
    assert container_quantity(unopened=0, opened=2) == 1


def test_scale_and_photo_of_the_same_bag_are_not_added():
    # The rice example: the scale says half a bag, then a photo of the same shelf sees one bag.
    readings = [Reading(HOME, 0.5, day(0)), Reading(HOME, 1, day(0) + timedelta(minutes=5))]

    assert estimate(readings, [], now=day(0) + timedelta(minutes=5)).on_hand == 1


def test_locations_add_up():
    readings = [Reading(HOME, 2, day(0)), Reading(GARAGE, 1, day(0))]

    assert estimate(readings, [], now=day(0)).on_hand == 3


def test_purchase_after_reading_adds_and_use_subtracts():
    readings = [Reading(HOME, 1, day(0))]
    changes = [Change("purchase", 2, day(1)), Change("use", 1, day(2))]

    assert estimate(readings, changes, now=day(3)).on_hand == 2


def test_purchase_before_latest_reading_is_already_counted():
    readings = [Reading(HOME, 3, day(2))]
    changes = [Change("purchase", 2, day(1))]

    assert estimate(readings, changes, now=day(2)).on_hand == 3


def test_usage_rate_from_two_readings():
    readings = [Reading(HOME, 3, day(0)), Reading(HOME, 1, day(10))]

    assert usage_rate(readings, []) == pytest.approx(0.2)


def test_usage_rate_counts_purchases_in_between():
    # 3 jars, bought 2, then 1 left: 4 used in 10 days.
    readings = [Reading(HOME, 3, day(0)), Reading(HOME, 1, day(10))]
    changes = [Change("purchase", 2, day(5))]

    assert usage_rate(readings, changes) == pytest.approx(0.4)


def test_usage_rate_does_not_double_count_logged_use():
    readings = [Reading(HOME, 3, day(0)), Reading(HOME, 1, day(10))]
    changes = [Change("use", 1, day(5))]

    assert usage_rate(readings, changes) == pytest.approx(0.2)


def test_usage_rate_needs_some_history():
    assert usage_rate([Reading(HOME, 3, day(0))], []) is None
    close = [Reading(HOME, 3, day(0)), Reading(HOME, 3, day(0) + timedelta(hours=1))]
    assert usage_rate(close, []) is None


def test_readings_at_any_frequency_give_the_same_rate():
    weekly = [Reading(HOME, 10 - d / 7, day(d)) for d in (0, 7, 14)]
    hourly = [Reading(HOME, 10 - h / 24 / 7, day(h / 24)) for h in range(0, 14 * 24 + 1)]

    assert usage_rate(weekly, []) == pytest.approx(1 / 7)
    assert usage_rate(hourly, []) == pytest.approx(1 / 7)


def test_flat_counts_mean_no_usage():
    readings = [Reading(HOME, 2, day(d)) for d in (0, 7, 14, 21)]

    assert usage_rate(readings, []) == 0


def test_estimate_projects_usage_since_last_reading():
    readings = [Reading(HOME, 3, day(0)), Reading(HOME, 2, day(7))]

    assert estimate(readings, [], now=day(14)).on_hand == pytest.approx(1)


def test_estimate_never_goes_negative():
    readings = [Reading(HOME, 3, day(0)), Reading(HOME, 2, day(7))]

    assert estimate(readings, [], now=day(100)).on_hand == 0


def test_unknown_location_is_only_a_lower_bound():
    known = Reading(HOME, 2, day(0))

    raised = estimate([known, Reading(None, 4, day(1))], [], now=day(1))
    not_lowered = estimate([known, Reading(None, 1, day(1))], [], now=day(1))

    assert raised.on_hand == 4
    assert not_lowered.on_hand == 2


def test_unknown_location_alone_gives_a_lower_bound():
    assert estimate([Reading(None, 2, day(0))], [], now=day(0)).on_hand == 2


def test_older_unknown_reading_is_superseded_by_a_newer_known_one():
    readings = [Reading(None, 4, day(0)), Reading(HOME, 1, day(1))]

    assert estimate(readings, [], now=day(1)).on_hand == 1


def test_future_readings_are_ignored():
    readings = [Reading(HOME, 2, day(0)), Reading(HOME, 9, day(5))]

    assert estimate(readings, [], now=day(1)).on_hand == 2


# The shopping list


def peanut_butter(on_hand, per_day=None):
    return estimate(
        [Reading(HOME, on_hand, day(0))]
        if per_day is None
        else [Reading(HOME, on_hand + per_day * 7, day(-7)), Reading(HOME, on_hand, day(0))],
        [],
        now=day(0),
    )


def test_item_without_minimum_is_never_listed():
    assert list_line(peanut_butter(0), None, None, day(0), day(7)) is None


def test_item_without_readings_is_never_listed():
    est = estimate([], [], now=day(0))

    assert list_line(est, 1, 3, day(0), day(7)) is None


def test_enough_on_hand_is_not_listed():
    assert list_line(peanut_butter(2), 1, 3, day(0), day(7)) is None


def test_low_stock_buys_up_to_maximum():
    line = list_line(peanut_butter(0.5), 1, 3, day(0), day(7))

    assert line.quantity == 2
    assert line.expected_at_shop == 0.5


def test_never_buys_past_maximum():
    line = list_line(peanut_butter(0.5), 1, 2, day(0), day(7))

    assert line.quantity == 1
    assert line.expected_at_shop + line.quantity <= 2


def test_skips_when_any_purchase_would_pass_maximum():
    assert list_line(peanut_butter(0.5), 1, 1, day(0), day(7)) is None


def test_without_maximum_buys_up_to_minimum():
    line = list_line(peanut_butter(0), 2, None, day(0), day(7))

    assert line.quantity == 2


def test_usage_until_shopping_date_is_counted():
    # 2 jars now, 1 jar used per 7 days; by the shop in 14 days there will be none.
    est = peanut_butter(2, per_day=1 / 7)

    soon = list_line(est, 1, 3, day(0), day(1))
    later = list_line(est, 1, 3, day(0), day(14))

    assert soon is None
    assert later.quantity == 3
    assert later.expected_at_shop == pytest.approx(0)


def test_slower_usage_stops_reordering():
    # A jar every two days at first, then the family stopped eating it: stock sat at 3 for
    # three weeks. Time since the last purchase alone never puts it back on the list.
    readings = [Reading(HOME, q, day(d)) for d, q in ((0, 5), (8, 1), (9, 3), (20, 3), (30, 3))]
    changes = [Change("purchase", 2, day(8.5))]
    est = estimate(readings, changes, now=day(30))

    assert est.usage_per_day < 0.25
    assert list_line(est, 2, 4, day(30), day(37)) is None
