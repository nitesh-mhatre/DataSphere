"""Tests for the news feed helpers."""

from dataspear.news import (
    NewsArticle,
    parse_rss,
    render_news_brief,
    score_article,
)

RSS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>NIFTY rallies on strong buying</title>
      <link>https://example.com/1</link>
      <pubDate>Mon, 01 Jun 2026 06:00:00 GMT</pubDate>
      <source url="https://example.com">Test Wire</source>
    </item>
    <item>
      <title>RBI rate hike triggers selloff</title>
      <link>https://example.com/2</link>
      <pubDate>Mon, 01 Jun 2026 07:00:00 GMT</pubDate>
      <source url="https://example.com">Test Wire</source>
    </item>
    <item>
      <title>NIFTY rallies on strong buying</title>
    </item>
  </channel>
</rss>
"""


class TestScoring:
    def test_bullish(self):
        sentiment, impact = score_article("NIFTY rallies on strong buying", "market")
        assert sentiment == "BULLISH"

    def test_bearish_high_impact(self):
        sentiment, impact = score_article("RBI rate hike triggers selloff", "market")
        assert sentiment == "BEARISH"
        assert impact == "HIGH"

    def test_geopolitical_bearish_is_high(self):
        _, impact = score_article("War concerns deepen", "geopolitical")
        assert impact == "HIGH"


class TestParseRss:
    def test_dedupes_and_scores(self):
        articles = parse_rss(RSS, category="market")
        assert len(articles) == 2
        assert articles[0].source == "Test Wire"
        assert articles[0].sentiment == "BULLISH"

    def test_bad_xml(self):
        assert parse_rss("<not xml") == []


class TestRenderBrief:
    def test_empty(self):
        assert render_news_brief([]) == "No market news available."

    def test_summary(self):
        articles = [
            NewsArticle(
                "a", "src", "", "", "market", sentiment="BULLISH", impact="HIGH"
            ),
            NewsArticle(
                "b", "src", "", "", "market", sentiment="BEARISH", impact="HIGH"
            ),
        ]
        text = render_news_brief(articles)
        assert "MARKET NEWS" in text
        assert "NEWS SENTIMENT" in text
