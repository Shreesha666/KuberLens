"""
Unit tests for core template tags: bull_icon, bear_icon, and trend_badge.
"""
import pytest
from apps.core.templatetags.core_tags import bear_icon, bull_icon, trend_badge


def test_bull_icon_renders_svg():
    result = bull_icon(size=14, css_class="custom-class")
    assert "<svg" in result
    assert "trend-bull-icon" in result
    assert "custom-class" in result
    assert 'width="14"' in result
    assert 'height="14"' in result
    assert 'viewBox="0 0 24 24"' in result
    assert "Layer_1" in result
    assert "</svg>" in result


def test_bear_icon_renders_svg():
    result = bear_icon(size=16, css_class="my-bear")
    assert "<svg" in result
    assert "trend-bear-icon" in result
    assert "my-bear" in result
    assert 'width="16"' in result
    assert 'height="16"' in result
    assert 'viewBox="0 0 24 24"' in result
    assert "Layer_1" in result
    assert "</svg>" in result


def test_trend_badge_bullish():
    result = trend_badge("BULLISH", size=14)
    assert "badge-bullish" in result
    assert "trend-bull-icon" in result
    assert "BULLISH" in result


def test_trend_badge_bearish():
    result = trend_badge("BEARISH_CROSS", size=12)
    assert "badge-bearish" in result
    assert "trend-bear-icon" in result
    assert "BEARISH" in result


def test_trend_badge_neutral():
    result = trend_badge("NEUTRAL")
    assert "badge-neutral-trend" in result
    assert "NEUTRAL" in result
