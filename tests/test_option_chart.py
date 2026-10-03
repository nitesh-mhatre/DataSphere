"""Tests for the option chart identifier and parser."""

from dataspear.nse.option_chart import (
    build_identifier,
    parse_chart_data,
)

RAW = {
    "grapthData": [[2000, 11.0], [1000, 10.5], [3000, 12.0]],
    "volume": [[1000, 100], [2000, 200], [3000, 300]],
    "closePrice": 9.5,
}


class TestBuildIdentifier:
    def test_ce(self):
        assert build_identifier("05-May-2026", 24000, "CE") == (
            "OPTIDXNIFTY05-05-2026CE24000.00"
        )

    def test_pe_lowercase_type(self):
        assert build_identifier("05-May-2026", 24050, "pe") == (
            "OPTIDXNIFTY05-05-2026PE24050.00"
        )

    def test_accepts_dd_mm_yyyy(self):
        # The option-chain rows return this format from the live NSE API.
        assert build_identifier("06-10-2026", 24000, "CE") == (
            "OPTIDXNIFTY06-10-2026CE24000.00"
        )

    def test_rejects_unknown_format(self):
        import pytest

        with pytest.raises(ValueError):
            build_identifier("not-a-date", 24000)


class TestParseChartData:
    def test_sorted_with_volume(self):
        chart = parse_chart_data(RAW, identifier="X", expiry="05-May-2026", strike=24000)
        assert len(chart.points) == 3
        assert [p.price for p in chart.points] == [10.5, 11.0, 12.0]
        assert chart.points[0].volume == 100
        assert chart.close_price == 9.5

    def test_aggregates(self):
        chart = parse_chart_data(RAW)
        assert chart.last_price == 12.0
        assert chart.high == 12.0
        assert chart.low == 10.5
        assert chart.total_volume == 600

    def test_empty(self):
        chart = parse_chart_data({})
        assert chart.points == []
        assert chart.last_price == 0.0

    def test_trend(self):
        rising = parse_chart_data(
            {"grapthData": [[i * 1000, 10 + i] for i in range(10)]}
        )
        assert rising.trend() == "UP"
