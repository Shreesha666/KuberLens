"""
Intelligent Stock Search Engine.
Provides multi-token matching, typo tolerance / fuzzy similarity scoring,
and on-demand dynamic lookup for newly listed / unseeded equities.
"""
import difflib
import logging
import re

from django.db.models import Q

from apps.instruments.models import Exchange, ExchangeListing, Instrument

logger = logging.getLogger(__name__)


def smart_stock_search(query: str, limit: int = 8, allow_external_lookup: bool = True) -> list[ExchangeListing]:
    """
    Intelligent stock search with:
    1. Direct exact symbol, prefix, and tokenized keyword matching.
    2. Typo-tolerant fuzzy matching (e.g. 'badhan bank' -> 'Bandhan Bank', 'relaince' -> 'Reliance').
    3. On-demand dynamic resolution for unseeded / newly listed Indian stocks (e.g. IPO stocks like 'URBANCO').
    """
    q = query.strip()
    if not q:
        return []

    q_lower = q.lower()
    q_words = [w for w in q_lower.split() if w]

    # 1. Exact & Prefix Matches (Highest Priority)
    exact_matches = list(
        ExchangeListing.objects.filter(is_tradeable=True)
        .filter(Q(symbol__iexact=q) | Q(instrument__display_name__iexact=q))
        .select_related("instrument", "exchange")[:limit]
    )
    seen_ids = {item.id for item in exact_matches}

    # Prefix matches (e.g. 'ioc', 'rel', 'tata')
    prefix_matches = list(
        ExchangeListing.objects.filter(is_tradeable=True)
        .filter(Q(symbol__istartswith=q) | Q(instrument__display_name__istartswith=q))
        .exclude(id__in=seen_ids)
        .select_related("instrument", "exchange")[:limit]
    )
    for item in prefix_matches:
        seen_ids.add(item.id)

    # Multi-token conjunction (every query word appears somewhere in symbol, display name, legal name, or isin)
    token_q = Q(is_tradeable=True)
    for word in q_words:
        token_q &= (
            Q(symbol__icontains=word)
            | Q(instrument__display_name__icontains=word)
            | Q(instrument__legal_name__icontains=word)
            | Q(instrument__isin__icontains=word)
        )
    token_matches = list(
        ExchangeListing.objects.filter(token_q)
        .exclude(id__in=seen_ids)
        .select_related("instrument", "exchange")[:limit]
    )
    for item in token_matches:
        seen_ids.add(item.id)

    results = exact_matches + prefix_matches + token_matches

    # 2. Typo-Tolerant Fuzzy Matching
    # If we have fewer than limit results, check for fuzzy/typo matches
    if len(results) < limit:
        all_tradeable = list(
            ExchangeListing.objects.filter(is_tradeable=True)
            .exclude(id__in=seen_ids)
            .select_related("instrument", "exchange")
        )
        scored_candidates = []
        for listing in all_tradeable:
            sym = listing.symbol.lower()
            disp = listing.instrument.display_name.lower()
            legal = listing.instrument.legal_name.lower()
            clean_legal = re.sub(r"\s+(limited|ltd\.?)$", "", legal, flags=re.IGNORECASE).strip()
            words_in_name = clean_legal.split() + disp.split() + [sym]

            # Whole string similarity
            whole_sym = difflib.SequenceMatcher(None, q_lower, sym).ratio()
            whole_disp = difflib.SequenceMatcher(None, q_lower, disp).ratio()
            whole_clean = difflib.SequenceMatcher(None, q_lower, clean_legal).ratio()

            # Word-by-word matching
            matched_words = 0
            total_word_ratio = 0.0
            for qw in q_words:
                best_w = 0.0
                for w in words_in_name:
                    r = difflib.SequenceMatcher(None, qw, w).ratio()
                    if r > best_w:
                        best_w = r
                if qw in sym or qw in disp or qw in clean_legal:
                    matched_words += 1
                    total_word_ratio += 1.0
                elif best_w >= 0.72:
                    matched_words += 1
                    total_word_ratio += best_w

            coverage = matched_words / len(q_words) if q_words else 0
            avg_sim = total_word_ratio / len(q_words) if q_words else 0
            is_nse_bonus = 0.25 if listing.exchange.code == "NSE" and not listing.symbol.isdigit() else 0.0

            score = (coverage * 3.0) + avg_sim + max(whole_sym, whole_disp, whole_clean) + is_nse_bonus
            if coverage >= 0.5 and avg_sim >= 0.5:
                scored_candidates.append((score, listing))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        for _, candidate in scored_candidates:
            if candidate.id not in seen_ids:
                seen_ids.add(candidate.id)
                results.append(candidate)
                if len(results) >= limit:
                    break

    # 3. On-Demand Dynamic Resolution (Fallback for unseeded / newly listed stocks)
    if not results and allow_external_lookup and len(q) >= 3:
        external_listing = resolve_and_register_stock(q)
        if external_listing and external_listing.id not in seen_ids:
            results.append(external_listing)

    return results[:limit]


def resolve_and_register_stock(query: str) -> ExchangeListing | None:
    """
    Dynamically looks up unseeded Indian equities via yfinance search or ticker lookup
    and registers them into the database so they are instantly searchable.
    """
    import yfinance as yf
    clean_sym = re.sub(r"[^A-Za-z0-9]", "", query).upper()

    nse = Exchange.objects.filter(code="NSE").first()
    if not nse:
        return None

    candidate_symbols = [clean_sym]

    try:
        s = yf.Search(query, max_results=3)
        for q_item in getattr(s, "quotes", []):
            sym = q_item.get("symbol", "")
            if sym.endswith((".NS", ".BO")):
                base_sym = sym.split(".")[0].upper()
                if base_sym not in candidate_symbols:
                    candidate_symbols.append(base_sym)
    except Exception as e:
        logger.debug("External symbol search error for '%s': %s", query, e)

    for sym in candidate_symbols:
        try:
            ticker = yf.Ticker(f"{sym}.NS")
            fast_info = getattr(ticker, "fast_info", None)
            last_p = getattr(fast_info, "last_price", None)
            if last_p is None:
                continue

            full_info = {}
            try:
                full_info = ticker.info or {}
            except Exception:
                pass

            legal_name = full_info.get("longName") or full_info.get("shortName") or sym
            display_name = re.sub(r"\s+(Limited|Ltd\.?)$", "", legal_name, flags=re.IGNORECASE).strip() or sym
            sector = full_info.get("sector") or "General"
            industry = full_info.get("industry") or "General"
            isin = full_info.get("isin") or f"INE{abs(hash(sym)) % 1000000000:09d}"

            inst, _ = Instrument.objects.get_or_create(
                isin=isin,
                defaults={
                    "display_name": display_name,
                    "legal_name": legal_name,
                    "sector": sector,
                    "industry": industry,
                    "market_cap_category": "MID",
                    "is_active": True,
                },
            )

            listing, _ = ExchangeListing.objects.get_or_create(
                symbol=sym,
                exchange=nse,
                defaults={
                    "instrument": inst,
                    "trading_symbol": f"{sym}-EQ",
                    "series_or_group": "EQ",
                    "is_primary": True,
                    "is_tradeable": True,
                },
            )

            # Auto-fetch historical candles & indicators for immediate chart and technical analytics
            try:
                from datetime import timedelta

                from django.utils import timezone

                from services.indicators.calculator import TechnicalIndicatorCalculator
                from services.market_data.service import MarketDataService

                end_d = timezone.now().date()
                start_d = end_d - timedelta(days=365)
                candles = MarketDataService.get_historical_candles(
                    listing, start_date=start_d, end_date=end_d, interval="1d", fetch_if_missing=True
                )
                if candles:
                    TechnicalIndicatorCalculator.compute_and_store_snapshots(listing, candles)
            except Exception as e:
                logger.debug("Initial candle backfill error for '%s': %s", sym, e)

            logger.info("Dynamically registered stock '%s' (%s) to universe", sym, display_name)
            return listing
        except Exception as e:
            logger.debug("Failed registering '%s': %s", sym, e)
            continue

    return None

