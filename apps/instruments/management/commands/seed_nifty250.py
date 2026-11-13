"""
Management command to seed the NIFTY Large & Midcap 250 universe
with 250-day historical candles, technical indicators, and fundamental snapshots.
"""
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import HistoricalCandle, MarketQuote
from services.fundamentals.analyzer import FundamentalAnalyzer
from services.indicators.calculator import TechnicalIndicatorCalculator

# Canonical list of 250 prominent Indian equities (NIFTY 100 Large Caps + NIFTY Midcap 150)
NIFTY_250_STOCKS = [
    # Top 100 Large Caps
    {"symbol": "RELIANCE", "name": "Reliance Industries", "sector": "Energy", "industry": "Oil & Gas Refining & Marketing", "cap": "LARGE", "price": 1334.90},
    {"symbol": "TCS", "name": "Tata Consultancy Services", "sector": "Information Technology", "industry": "IT Services & Consulting", "cap": "LARGE", "price": 4150.00},
    {"symbol": "HDFCBANK", "name": "HDFC Bank", "sector": "Financial Services", "industry": "Private Sector Bank", "cap": "LARGE", "price": 1720.00},
    {"symbol": "ICICIBANK", "name": "ICICI Bank", "sector": "Financial Services", "industry": "Private Sector Bank", "cap": "LARGE", "price": 1280.00},
    {"symbol": "BHARTIARTL", "name": "Bharti Airtel", "sector": "Telecommunication", "industry": "Telecom Services", "cap": "LARGE", "price": 1650.00},
    {"symbol": "INFY", "name": "Infosys", "sector": "Information Technology", "industry": "IT Services & Consulting", "cap": "LARGE", "price": 1860.00},
    {"symbol": "ITC", "name": "ITC Limited", "sector": "Consumer Goods", "industry": "Diversified FMCG", "cap": "LARGE", "price": 490.00},
    {"symbol": "LT", "name": "Larsen & Toubro", "sector": "Construction", "industry": "Engineering & Construction", "cap": "LARGE", "price": 3650.00},
    {"symbol": "SBIN", "name": "State Bank of India", "sector": "Financial Services", "industry": "Public Sector Bank", "cap": "LARGE", "price": 840.00},
    {"symbol": "HINDUNILVR", "name": "Hindustan Unilever", "sector": "Consumer Goods", "industry": "Diversified FMCG", "cap": "LARGE", "price": 2480.00},
    {"symbol": "BAJFINANCE", "name": "Bajaj Finance", "sector": "Financial Services", "industry": "NBFC", "cap": "LARGE", "price": 6850.00},
    {"symbol": "MARUTI", "name": "Maruti Suzuki", "sector": "Automobile", "industry": "Passenger Cars", "cap": "LARGE", "price": 11450.00},
    {"symbol": "HCLTECH", "name": "HCL Technologies", "sector": "Information Technology", "industry": "IT Services", "cap": "LARGE", "price": 1820.00},
    {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical", "sector": "Healthcare", "industry": "Pharmaceuticals", "cap": "LARGE", "price": 1790.00},
    {"symbol": "TATAMOTORS", "name": "Tata Motors", "sector": "Automobile", "industry": "Automobiles", "cap": "LARGE", "price": 980.00},
    {"symbol": "NTPC", "name": "NTPC Limited", "sector": "Power", "industry": "Power Generation", "cap": "LARGE", "price": 385.00},
    {"symbol": "AXISBANK", "name": "Axis Bank", "sector": "Financial Services", "industry": "Private Sector Bank", "cap": "LARGE", "price": 1180.00},
    {"symbol": "KOTAKBANK", "name": "Kotak Mahindra Bank", "sector": "Financial Services", "industry": "Private Sector Bank", "cap": "LARGE", "price": 1780.00},
    {"symbol": "TITAN", "name": "Titan Company", "sector": "Consumer Durables", "industry": "Gems & Jewellery", "cap": "LARGE", "price": 3280.00},
    {"symbol": "ONGC", "name": "Oil & Natural Gas Corp", "sector": "Energy", "industry": "Oil Exploration & Production", "cap": "LARGE", "price": 265.00},
    {"symbol": "ADANIENT", "name": "Adani Enterprises", "sector": "Metals & Mining", "industry": "Trading - Minerals", "cap": "LARGE", "price": 2980.00},
    {"symbol": "ADANIPORTS", "name": "Adani Ports & SEZ", "sector": "Services", "industry": "Port Operations", "cap": "LARGE", "price": 1380.00},
    {"symbol": "COALINDIA", "name": "Coal India", "sector": "Energy", "industry": "Coal", "cap": "LARGE", "price": 406.30},
    {"symbol": "POWERGRID", "name": "Power Grid Corporation", "sector": "Power", "industry": "Power Transmission", "cap": "LARGE", "price": 320.00},
    {"symbol": "TATASTEEL", "name": "Tata Steel", "sector": "Metals & Mining", "industry": "Iron & Steel", "cap": "LARGE", "price": 152.00},
    {"symbol": "M&M", "name": "Mahindra & Mahindra", "sector": "Automobile", "industry": "Commercial & Passenger Vehicles", "cap": "LARGE", "price": 2890.00},
    {"symbol": "BAJAJFINSV", "name": "Bajaj Finserv", "sector": "Financial Services", "industry": "Financial Holding", "cap": "LARGE", "price": 1620.00},
    {"symbol": "JSWSTEEL", "name": "JSW Steel", "sector": "Metals & Mining", "industry": "Iron & Steel", "cap": "LARGE", "price": 960.00},
    {"symbol": "ASIANPAINT", "name": "Asian Paints", "sector": "Consumer Goods", "industry": "Paints", "cap": "LARGE", "price": 2520.00},
    {"symbol": "NESTLEIND", "name": "Nestle India", "sector": "Consumer Goods", "industry": "Packaged Foods", "cap": "LARGE", "price": 2280.00},
    {"symbol": "GRASIM", "name": "Grasim Industries", "sector": "Materials", "industry": "Diversified Chemicals & Cement", "cap": "LARGE", "price": 2540.00},
    {"symbol": "TECHM", "name": "Tech Mahindra", "sector": "Information Technology", "industry": "IT Services", "cap": "LARGE", "price": 1680.00},
    {"symbol": "ULTRACEMCO", "name": "UltraTech Cement", "sector": "Materials", "industry": "Cement", "cap": "LARGE", "price": 11200.00},
    {"symbol": "WIPRO", "name": "Wipro Limited", "sector": "Information Technology", "industry": "IT Services", "cap": "LARGE", "price": 540.00},
    {"symbol": "HINDALCO", "name": "Hindalco Industries", "sector": "Metals & Mining", "industry": "Aluminium", "cap": "LARGE", "price": 680.00},
    {"symbol": "CIPLA", "name": "Cipla Limited", "sector": "Healthcare", "industry": "Pharmaceuticals", "cap": "LARGE", "price": 1540.00},
    {"symbol": "INDUSINDBK", "name": "IndusInd Bank", "sector": "Financial Services", "industry": "Private Sector Bank", "cap": "LARGE", "price": 1120.00},
    {"symbol": "APOLLOHOSP", "name": "Apollo Hospitals", "sector": "Healthcare", "industry": "Healthcare Facilities", "cap": "LARGE", "price": 7150.00},
    {"symbol": "HEROMOTOCO", "name": "Hero MotoCorp", "sector": "Automobile", "industry": "2 & 3 Wheelers", "cap": "LARGE", "price": 4850.00},
    {"symbol": "EICHERMOT", "name": "Eicher Motors", "sector": "Automobile", "industry": "2 & 3 Wheelers", "cap": "LARGE", "price": 4920.00},
    {"symbol": "DRREDDY", "name": "Dr. Reddy's Laboratories", "sector": "Healthcare", "industry": "Pharmaceuticals", "cap": "LARGE", "price": 1280.00},
    {"symbol": "DIVISLAB", "name": "Divi's Laboratories", "sector": "Healthcare", "industry": "Active Pharma Ingredients", "cap": "LARGE", "price": 5850.00},
    {"symbol": "BPCL", "name": "Bharat Petroleum Corp", "sector": "Energy", "industry": "Oil Refining & Marketing", "cap": "LARGE", "price": 315.00},
    {"symbol": "TRENT", "name": "Trent Limited", "sector": "Consumer Services", "industry": "Retail", "cap": "LARGE", "price": 6850.00},
    {"symbol": "BEL", "name": "Bharat Electronics", "sector": "Capital Goods", "industry": "Aerospace & Defense", "cap": "LARGE", "price": 295.00},
    {"symbol": "SHRIRAMFIN", "name": "Shriram Finance", "sector": "Financial Services", "industry": "NBFC", "cap": "LARGE", "price": 3180.00},
    {"symbol": "TATACONSUM", "name": "Tata Consumer Products", "sector": "Consumer Goods", "industry": "Tea & Packaged Food", "cap": "LARGE", "price": 1020.00},
    {"symbol": "BRITANNIA", "name": "Britannia Industries", "sector": "Consumer Goods", "industry": "Bakery Products", "cap": "LARGE", "price": 5120.00},
    {"symbol": "SBILIFE", "name": "SBI Life Insurance", "sector": "Financial Services", "industry": "Life Insurance", "cap": "LARGE", "price": 1580.00},
    {"symbol": "HDFCLIFE", "name": "HDFC Life Insurance", "sector": "Financial Services", "industry": "Life Insurance", "cap": "LARGE", "price": 710.00},
    {"symbol": "ABB", "name": "ABB India", "sector": "Capital Goods", "industry": "Heavy Electrical Equipment", "cap": "LARGE", "price": 7450.00},
    {"symbol": "ADANIENSOL", "name": "Adani Energy Solutions", "sector": "Power", "industry": "Power Transmission", "cap": "LARGE", "price": 980.00},
    {"symbol": "ADANIGREEN", "name": "Adani Green Energy", "sector": "Power", "industry": "Renewable Power", "cap": "LARGE", "price": 1640.00},
    {"symbol": "AMBUJACEM", "name": "Ambuja Cements", "sector": "Materials", "industry": "Cement", "cap": "LARGE", "price": 580.00},
    {"symbol": "ATGL", "name": "Adani Total Gas", "sector": "Energy", "industry": "City Gas Distribution", "cap": "LARGE", "price": 710.00},
    {"symbol": "BANKBARODA", "name": "Bank of Baroda", "sector": "Financial Services", "industry": "Public Sector Bank", "cap": "LARGE", "price": 245.00},
    {"symbol": "BOSCHLTD", "name": "Bosch Limited", "sector": "Automobile", "industry": "Auto Parts & Equipment", "cap": "LARGE", "price": 33500.00},
    {"symbol": "CANBK", "name": "Canara Bank", "sector": "Financial Services", "industry": "Public Sector Bank", "cap": "LARGE", "price": 105.00},
    {"symbol": "CHOLAFIN", "name": "Cholamandalam Investment", "sector": "Financial Services", "industry": "NBFC", "cap": "LARGE", "price": 1280.00},
    {"symbol": "COLPAL", "name": "Colgate-Palmolive India", "sector": "Consumer Goods", "industry": "Personal Care", "cap": "LARGE", "price": 2850.00},
    {"symbol": "DABUR", "name": "Dabur India", "sector": "Consumer Goods", "industry": "Personal Care & Herbal", "cap": "LARGE", "price": 520.00},
    {"symbol": "DLF", "name": "DLF Limited", "sector": "Realty", "industry": "Real Estate Development", "cap": "LARGE", "price": 820.00},
    {"symbol": "GAIL", "name": "GAIL (India) Limited", "sector": "Energy", "industry": "Natural Gas Transmission", "cap": "LARGE", "price": 195.00},
    {"symbol": "GODREJCP", "name": "Godrej Consumer Products", "sector": "Consumer Goods", "industry": "Personal Care", "cap": "LARGE", "price": 1240.00},
    {"symbol": "HAVELLS", "name": "Havells India", "sector": "Consumer Durables", "industry": "Electric Consumer Durables", "cap": "LARGE", "price": 1680.00},
    {"symbol": "HAL", "name": "Hindustan Aeronautics", "sector": "Capital Goods", "industry": "Aerospace & Defense", "cap": "LARGE", "price": 4350.00},
    {"symbol": "ICICIGI", "name": "ICICI Lombard General Ins", "sector": "Financial Services", "industry": "General Insurance", "cap": "LARGE", "price": 1890.00},
    {"symbol": "ICICIPRULI", "name": "ICICI Prudential Life Ins", "sector": "Financial Services", "industry": "Life Insurance", "cap": "LARGE", "price": 680.00},
    {"symbol": "IOC", "name": "Indian Oil Corporation", "sector": "Energy", "industry": "Oil Refining & Marketing", "cap": "LARGE", "price": 148.00},
    {"symbol": "IRCTC", "name": "IRCTC Limited", "sector": "Services", "industry": "Online Ticketing & Catering", "cap": "LARGE", "price": 860.00},
    {"symbol": "IRFC", "name": "Indian Railway Finance", "sector": "Financial Services", "industry": "Infrastructure Finance", "cap": "LARGE", "price": 148.00},
    {"symbol": "JINDALSTEL", "name": "Jindal Steel & Power", "sector": "Metals & Mining", "industry": "Iron & Steel", "cap": "LARGE", "price": 940.00},
    {"symbol": "JIOFIN", "name": "Jio Financial Services", "sector": "Financial Services", "industry": "Financial Services Holding", "cap": "LARGE", "price": 315.00},
    {"symbol": "LICI", "name": "Life Insurance Corp of India", "sector": "Financial Services", "industry": "Life Insurance", "cap": "LARGE", "price": 920.00},
    {"symbol": "LTIM", "name": "LTIMindtree Limited", "sector": "Information Technology", "industry": "IT Services", "cap": "LARGE", "price": 5950.00},
    {"symbol": "MARICO", "name": "Marico Limited", "sector": "Consumer Goods", "industry": "Edible Oils & Hair Care", "cap": "LARGE", "price": 640.00},
    {"symbol": "MOTHERSON", "name": "Samvardhana Motherson", "sector": "Automobile", "industry": "Auto Parts", "cap": "LARGE", "price": 165.00},
    {"symbol": "MUTHOOTFIN", "name": "Muthoot Finance", "sector": "Financial Services", "industry": "Gold Loan NBFC", "cap": "LARGE", "price": 1940.00},
    {"symbol": "NAUKRI", "name": "Info Edge (India)", "sector": "Consumer Services", "industry": "Internet Portals", "cap": "LARGE", "price": 7850.00},
    {"symbol": "NHPC", "name": "NHPC Limited", "sector": "Power", "industry": "Hydroelectric Power", "cap": "LARGE", "price": 85.00},
    {"symbol": "PIDILITIND", "name": "Pidilite Industries", "sector": "Chemicals", "industry": "Adhesives & Sealants", "cap": "LARGE", "price": 3120.00},
    {"symbol": "PFC", "name": "Power Finance Corporation", "sector": "Financial Services", "industry": "Infrastructure Finance", "cap": "LARGE", "price": 485.00},
    {"symbol": "PNB", "name": "Punjab National Bank", "sector": "Financial Services", "industry": "Public Sector Bank", "cap": "LARGE", "price": 105.00},
    {"symbol": "RECLTD", "name": "REC Limited", "sector": "Financial Services", "industry": "Power Infrastructure Finance", "cap": "LARGE", "price": 520.00},
    {"symbol": "SBICARD", "name": "SBI Cards & Payment", "sector": "Financial Services", "industry": "Credit Cards", "cap": "LARGE", "price": 690.00},
    {"symbol": "SIEMENS", "name": "Siemens Limited", "sector": "Capital Goods", "industry": "Industrial Equipment", "cap": "LARGE", "price": 7250.00},
    {"symbol": "SRF", "name": "SRF Limited", "sector": "Chemicals", "industry": "Specialty Chemicals", "cap": "LARGE", "price": 2240.00},
    {"symbol": "TVSMOTOR", "name": "TVS Motor Company", "sector": "Automobile", "industry": "2 & 3 Wheelers", "cap": "LARGE", "price": 2450.00},
    {"symbol": "UNITDSPR", "name": "United Spirits", "sector": "Consumer Goods", "industry": "Beverages - Distilleries", "cap": "LARGE", "price": 1480.00},
    {"symbol": "VBL", "name": "Varun Beverages", "sector": "Consumer Goods", "industry": "Beverages - Soft Drinks", "cap": "LARGE", "price": 620.00},
    {"symbol": "VEDL", "name": "Vedanta Limited", "sector": "Metals & Mining", "industry": "Diversified Metals", "cap": "LARGE", "price": 465.00},
    {"symbol": "ZOMATO", "name": "Zomato Limited", "sector": "Consumer Services", "industry": "Food Delivery & Quick Commerce", "cap": "LARGE", "price": 265.00},
    {"symbol": "ZYDUSLIFE", "name": "Zydus Lifesciences", "sector": "Healthcare", "industry": "Pharmaceuticals", "cap": "LARGE", "price": 980.00},
    {"symbol": "INDIGO", "name": "InterGlobe Aviation", "sector": "Services", "industry": "Airlines", "cap": "LARGE", "price": 4180.00},
    {"symbol": "BERGEPAINT", "name": "Berger Paints India", "sector": "Consumer Goods", "industry": "Paints", "cap": "LARGE", "price": 490.00},
    {"symbol": "TORNTPHARM", "name": "Torrent Pharmaceuticals", "sector": "Healthcare", "industry": "Pharmaceuticals", "cap": "LARGE", "price": 3280.00},
    {"symbol": "POLYCAB", "name": "Polycab India", "sector": "Capital Goods", "industry": "Cables & Electricals", "cap": "LARGE", "price": 6850.00},
    {"symbol": "CGPOWER", "name": "CG Power & Industrial", "sector": "Capital Goods", "industry": "Heavy Electrical Equipment", "cap": "LARGE", "price": 740.00},
    {"symbol": "BAJAJHLDNG", "name": "Bajaj Holdings & Inv", "sector": "Financial Services", "industry": "Investment Holding", "cap": "LARGE", "price": 10200.00},
    {"symbol": "PGHH", "name": "Procter & Gamble Hygiene", "sector": "Consumer Goods", "industry": "Personal Care", "cap": "LARGE", "price": 16400.00},

    # NIFTY Midcap 150 Equities (Mid Caps 101-250)
    {"symbol": "AUBANK", "name": "AU Small Finance Bank", "sector": "Financial Services", "industry": "Small Finance Bank", "cap": "MID", "price": 640.00},
    {"symbol": "ASTRAL", "name": "Astral Limited", "sector": "Capital Goods", "industry": "Piping & Building Materials", "cap": "MID", "price": 1820.00},
    {"symbol": "AUROPHARMA", "name": "Aurobindo Pharma", "sector": "Healthcare", "industry": "Pharmaceuticals", "cap": "MID", "price": 1280.00},
    {"symbol": "BALKRISIND", "name": "Balkrishna Industries", "sector": "Automobile", "industry": "Tyres - Off-Highway", "cap": "MID", "price": 2850.00},
    {"symbol": "BANDHANBNK", "name": "Bandhan Bank", "sector": "Financial Services", "industry": "Private Sector Bank", "cap": "MID", "price": 172.00},
    {"symbol": "BANKINDIA", "name": "Bank of India", "sector": "Financial Services", "industry": "Public Sector Bank", "cap": "MID", "price": 150.60},
    {"symbol": "BATAINDIA", "name": "Bata India", "sector": "Consumer Goods", "industry": "Footwear", "cap": "MID", "price": 1380.00},
    {"symbol": "BHARATFORG", "name": "Bharat Forge", "sector": "Capital Goods", "industry": "Forgings & Auto Components", "cap": "MID", "price": 1420.00},
    {"symbol": "BHEL", "name": "Bharat Heavy Electricals", "sector": "Capital Goods", "industry": "Power Equipment", "cap": "MID", "price": 240.00},
    {"symbol": "BIOCON", "name": "Biocon Limited", "sector": "Healthcare", "industry": "Biotechnology & Biosimilars", "cap": "MID", "price": 340.00},
    {"symbol": "CANFINHOME", "name": "Can Fin Homes", "sector": "Financial Services", "industry": "Housing Finance", "cap": "MID", "price": 820.00},
    {"symbol": "CLEAN", "name": "Clean Science & Tech", "sector": "Chemicals", "industry": "Specialty Chemicals", "cap": "MID", "price": 1420.00},
    {"symbol": "CONCOR", "name": "Container Corp of India", "sector": "Services", "industry": "Logistics & Freight", "cap": "MID", "price": 840.00},
    {"symbol": "COROMANDEL", "name": "Coromandel International", "sector": "Chemicals", "industry": "Agrochemicals & Fertilizers", "cap": "MID", "price": 1680.00},
    {"symbol": "CROMPTON", "name": "Crompton Greaves Consumer", "sector": "Consumer Durables", "industry": "Electrical Appliances", "cap": "MID", "price": 395.00},
    {"symbol": "CUMMINSIND", "name": "Cummins India", "sector": "Capital Goods", "industry": "Diesel Engines & Generators", "cap": "MID", "price": 3650.00},
    {"symbol": "DEEPAKNTR", "name": "Deepak Nitrite", "sector": "Chemicals", "industry": "Phenolics & Intermediates", "cap": "MID", "price": 2720.00},
    {"symbol": "DELHIVERY", "name": "Delhivery Limited", "sector": "Services", "industry": "Express Parcel Logistics", "cap": "MID", "price": 380.00},
    {"symbol": "DEVYANI", "name": "Devyani International", "sector": "Consumer Services", "industry": "QSR Franchises", "cap": "MID", "price": 165.00},
    {"symbol": "DIXON", "name": "Dixon Technologies", "sector": "Consumer Durables", "industry": "Electronics Manufacturing", "cap": "MID", "price": 14850.00},
    {"symbol": "EIHOTEL", "name": "EIH Limited (Oberoi)", "sector": "Consumer Services", "industry": "Hotels & Resorts", "cap": "MID", "price": 312.95},
    {"symbol": "ESCORTS", "name": "Escorts Kubota", "sector": "Automobile", "industry": "Tractors & Agri Equipment", "cap": "MID", "price": 3820.00},
    {"symbol": "EXIDEIND", "name": "Exide Industries", "sector": "Automobile", "industry": "Storage Batteries", "cap": "MID", "price": 440.00},
    {"symbol": "FEDERALBNK", "name": "Federal Bank", "sector": "Financial Services", "industry": "Private Sector Bank", "cap": "MID", "price": 205.00},
    {"symbol": "FORTIS", "name": "Fortis Healthcare", "sector": "Healthcare", "industry": "Hospitals", "cap": "MID", "price": 620.00},
    {"symbol": "GLENMARK", "name": "Glenmark Pharmaceuticals", "sector": "Healthcare", "industry": "Formulations & Discovery", "cap": "MID", "price": 1540.00},
    {"symbol": "GMRINFRA", "name": "GMR Airports Infrastructure", "sector": "Services", "industry": "Airport Operations", "cap": "MID", "price": 82.00},
    {"symbol": "GODREJPROP", "name": "Godrej Properties", "sector": "Realty", "industry": "Residential Real Estate", "cap": "MID", "price": 2840.00},
    {"symbol": "GUJGASLTD", "name": "Gujarat Gas Limited", "sector": "Energy", "industry": "City Gas Distribution", "cap": "MID", "price": 540.00},
    {"symbol": "HDFCAMC", "name": "HDFC Asset Management", "sector": "Financial Services", "industry": "Asset Management", "cap": "MID", "price": 4250.00},
    {"symbol": "HINDPETRO", "name": "Hindustan Petroleum", "sector": "Energy", "industry": "Oil Refining & Marketing", "cap": "MID", "price": 380.00},
    {"symbol": "IDFCFIRSTB", "name": "IDFC FIRST Bank", "sector": "Financial Services", "industry": "Private Sector Bank", "cap": "MID", "price": 68.00},
    {"symbol": "INDIANB", "name": "Indian Bank", "sector": "Financial Services", "industry": "Public Sector Bank", "cap": "MID", "price": 540.00},
    {"symbol": "IPCALAB", "name": "IPCA Laboratories", "sector": "Healthcare", "industry": "Formulations & APIs", "cap": "MID", "price": 1580.00},
    {"symbol": "JUBLFOOD", "name": "Jubilant FoodWorks", "sector": "Consumer Services", "industry": "QSR (Domino's Pizza)", "cap": "MID", "price": 580.00},
    {"symbol": "KPITTECH", "name": "KPIT Technologies", "sector": "Information Technology", "industry": "Automotive Software", "cap": "MID", "price": 1420.00},
    {"symbol": "KALYANKJIL", "name": "Kalyan Jewellers", "sector": "Consumer Durables", "industry": "Gems & Jewellery", "cap": "MID", "price": 680.00},
    {"symbol": "KEI", "name": "KEI Industries", "sector": "Capital Goods", "industry": "Cables & Wires", "cap": "MID", "price": 4250.00},
    {"symbol": "L&TFH", "name": "L&T Finance", "sector": "Financial Services", "industry": "Retail NBFC", "cap": "MID", "price": 148.00},
    {"symbol": "LAURUSLABS", "name": "Laurus Labs", "sector": "Healthcare", "industry": "ARV APIs & Synthesis", "cap": "MID", "price": 460.00},
    {"symbol": "LICHSGFIN", "name": "LIC Housing Finance", "sector": "Financial Services", "industry": "Housing Finance", "cap": "MID", "price": 620.00},
    {"symbol": "LUPIN", "name": "Lupin Limited", "sector": "Healthcare", "industry": "Generic Pharmaceuticals", "cap": "MID", "price": 2180.00},
    {"symbol": "MAXHEALTH", "name": "Max Healthcare Institute", "sector": "Healthcare", "industry": "Hospital Network", "cap": "MID", "price": 980.00},
    {"symbol": "METROPOLIS", "name": "Metropolis Healthcare", "sector": "Healthcare", "industry": "Diagnostic Labs", "cap": "MID", "price": 2150.00},
    {"symbol": "MFSL", "name": "Max Financial Services", "sector": "Financial Services", "industry": "Life Insurance (Max Life)", "cap": "MID", "price": 1240.00},
    {"symbol": "MPHASIS", "name": "Mphasis Limited", "sector": "Information Technology", "industry": "Cloud & Cognitive IT", "cap": "MID", "price": 2840.00},
    {"symbol": "MRF", "name": "MRF Limited", "sector": "Automobile", "industry": "Tyres", "cap": "MID", "price": 128000.00},
    {"symbol": "NATCOPHARM", "name": "Natco Pharma", "sector": "Healthcare", "industry": "Oncology Formulations", "cap": "MID", "price": 1380.00},
    {"symbol": "NAVINFLUOR", "name": "Navin Fluorine Int", "sector": "Chemicals", "industry": "Fluorochemicals", "cap": "MID", "price": 3450.00},
    {"symbol": "OBEROIRLTY", "name": "Oberoi Realty", "sector": "Realty", "industry": "Premium Real Estate", "cap": "MID", "price": 1950.00},
    {"symbol": "OFSS", "name": "Oracle Financial Services", "sector": "Information Technology", "industry": "Banking Software Products", "cap": "MID", "price": 11800.00},
    {"symbol": "PAGEIND", "name": "Page Industries (Jockey)", "sector": "Consumer Goods", "industry": "Apparel & Innerwear", "cap": "MID", "price": 44500.00},
    {"symbol": "PERSISTENT", "name": "Persistent Systems", "sector": "Information Technology", "industry": "Digital Engineering Services", "cap": "MID", "price": 5650.00},
    {"symbol": "PETRONET", "name": "Petronet LNG", "sector": "Energy", "industry": "LNG Regasification", "cap": "MID", "price": 320.00},
    {"symbol": "PFIZER", "name": "Pfizer Limited", "sector": "Healthcare", "industry": "Pharmaceuticals", "cap": "MID", "price": 5450.00},
    {"symbol": "PHOENIXLTD", "name": "The Phoenix Mills", "sector": "Realty", "industry": "Retail Mall Development", "cap": "MID", "price": 1680.00},
    {"symbol": "PIIND", "name": "PI Industries", "sector": "Chemicals", "industry": "Agrochemicals CSM", "cap": "MID", "price": 4350.00},
    {"symbol": "POONAWALLA", "name": "Poonawalla Fincorp", "sector": "Financial Services", "industry": "Consumer & SME NBFC", "cap": "MID", "price": 340.00},
    {"symbol": "PRESTIGE", "name": "Prestige Estates Projects", "sector": "Realty", "industry": "Residential & Commercial", "cap": "MID", "price": 1720.00},
    {"symbol": "RAMCOCEM", "name": "The Ramco Cements", "sector": "Materials", "industry": "Cement", "cap": "MID", "price": 910.00},
    {"symbol": "REDINGTON", "name": "Redington Limited", "sector": "Services", "industry": "Technology Distribution", "cap": "MID", "price": 344.30},
    {"symbol": "RENUKA", "name": "Shree Renuka Sugars", "sector": "Consumer Goods", "industry": "Sugar Refining & Ethanol", "cap": "MID", "price": 18.85},
    {"symbol": "SAIL", "name": "Steel Authority of India", "sector": "Metals & Mining", "industry": "Public Sector Steel", "cap": "MID", "price": 118.00},
    {"symbol": "SONACOMS", "name": "Sona BLW Precision", "sector": "Automobile", "industry": "EV Driveline Systems", "cap": "MID", "price": 680.00},
    {"symbol": "SUNTV", "name": "Sun TV Network", "sector": "Consumer Services", "industry": "Broadcasting & Content", "cap": "MID", "price": 780.00},
    {"symbol": "SWSOLAR", "name": "Sterling & Wilson Solar", "sector": "Power", "industry": "Solar EPC", "cap": "MID", "price": 163.50},
    {"symbol": "SYNGENE", "name": "Syngene International", "sector": "Healthcare", "industry": "Contract Research (CRO)", "cap": "MID", "price": 890.00},
    {"symbol": "TATACHEM", "name": "Tata Chemicals", "sector": "Chemicals", "industry": "Soda Ash & Bicarb", "cap": "MID", "price": 1020.00},
    {"symbol": "TATACOMM", "name": "Tata Communications", "sector": "Telecommunication", "industry": "Enterprise Digital Infra", "cap": "MID", "price": 1850.00},
    {"symbol": "TATAELXSI", "name": "Tata Elxsi", "sector": "Information Technology", "industry": "Design & Technology Services", "cap": "MID", "price": 6850.00},
    {"symbol": "TATAPOWER", "name": "Tata Power Company", "sector": "Power", "industry": "Integrated Power & EV Infra", "cap": "MID", "price": 415.00},
    {"symbol": "THERMAX", "name": "Thermax Limited", "sector": "Capital Goods", "industry": "Boilers & Green Energy", "cap": "MID", "price": 4950.00},
    {"symbol": "TIINDIA", "name": "Tube Investments of India", "sector": "Automobile", "industry": "Precision Tubes & Cycles", "cap": "MID", "price": 3650.00},
    {"symbol": "TORNTPOWER", "name": "Torrent Power", "sector": "Power", "industry": "Power Distribution & Solar", "cap": "MID", "price": 1680.00},
    {"symbol": "TRIDENT", "name": "Trident Limited", "sector": "Consumer Goods", "industry": "Home Textiles & Paper", "cap": "MID", "price": 23.42},
    {"symbol": "TRITURBINE", "name": "Triveni Turbine", "sector": "Capital Goods", "industry": "Steam Turbines", "cap": "MID", "price": 640.00},
    {"symbol": "UNIONBANK", "name": "Union Bank of India", "sector": "Financial Services", "industry": "Public Sector Bank", "cap": "MID", "price": 115.00},
    {"symbol": "UPL", "name": "UPL Limited", "sector": "Chemicals", "industry": "Crop Protection Solutions", "cap": "MID", "price": 540.00},
    {"symbol": "VOLTAS", "name": "Voltas Limited", "sector": "Consumer Durables", "industry": "Room Air Conditioners", "cap": "MID", "price": 1720.00},
    {"symbol": "WHIRLPOOL", "name": "Whirlpool of India", "sector": "Consumer Durables", "industry": "Home Appliances", "cap": "MID", "price": 2150.00},
    {"symbol": "YESBANK", "name": "Yes Bank", "sector": "Financial Services", "industry": "Private Sector Bank", "cap": "MID", "price": 20.50},
    {"symbol": "ZEEL", "name": "Zee Entertainment", "sector": "Consumer Services", "industry": "Media Entertainment", "cap": "MID", "price": 118.00},
    {"symbol": "MMTC", "name": "MMTC Limited", "sector": "Services", "industry": "Trading - Minerals & Metals", "cap": "MID", "price": 54.20},
    {"symbol": "MID150CASE", "name": "Midcap Momentum ETF", "sector": "Financial Services", "industry": "Exchange Traded Fund", "cap": "MID", "price": 11.38},
    {"symbol": "MOREPENLAB", "name": "Morepen Laboratories", "sector": "Healthcare", "industry": "Diagnostic Devices & APIs", "cap": "MID", "price": 96.70},
    {"symbol": "NRBBEARING", "name": "NRB Bearings", "sector": "Automobile", "industry": "Needle & Roller Bearings", "cap": "MID", "price": 431.70},
    {"symbol": "PATELENG", "name": "Patel Engineering", "sector": "Construction", "industry": "Hydro & Tunnel Construction", "cap": "MID", "price": 25.70},
    {"symbol": "FCL", "name": "Finolex Cables", "sector": "Capital Goods", "industry": "Electrical & Telecom Cables", "cap": "MID", "price": 51.65},
    {"symbol": "MICEL", "name": "MIC Electronics", "sector": "Capital Goods", "industry": "LED Displays & Railway Telecom", "cap": "MID", "price": 39.50},
    {"symbol": "TATSILV", "name": "Tata Silver ETF", "sector": "Financial Services", "industry": "Commodity ETF", "cap": "MID", "price": 18.00},
    {"symbol": "SUZLON", "name": "Suzlon Energy", "sector": "Power", "industry": "Wind Energy Turbines", "cap": "MID", "price": 64.00},
    {"symbol": "NH", "name": "Narayana Hrudayalaya", "sector": "Healthcare", "industry": "Cardiac & Multi-specialty", "cap": "MID", "price": 1240.00},
    {"symbol": "KEC", "name": "KEC International", "sector": "Capital Goods", "industry": "Power Transmission EPC", "cap": "MID", "price": 980.00},
    {"symbol": "GLS", "name": "Glenmark Life Sciences", "sector": "Healthcare", "industry": "Active Pharma Ingredients", "cap": "MID", "price": 1050.00},
    {"symbol": "JBCHEPHARM", "name": "JB Chemicals & Pharma", "sector": "Healthcare", "industry": "Formulations & Exports", "cap": "MID", "price": 1840.00},
    {"symbol": "AJANTPHARM", "name": "Ajanta Pharma", "sector": "Healthcare", "industry": "Branded Generics", "cap": "MID", "price": 2850.00},
    {"symbol": "ALKYLAMINE", "name": "Alkyl Amines Chemicals", "sector": "Chemicals", "industry": "Aliphatic Amines", "cap": "MID", "price": 1940.00},
    {"symbol": "ATUL", "name": "Atul Limited", "sector": "Chemicals", "industry": "Aromatics & Crop Protection", "cap": "MID", "price": 7250.00},
    {"symbol": "FINEORG", "name": "Fine Organic Industries", "sector": "Chemicals", "industry": "Oleochemical Additives", "cap": "MID", "price": 4920.00},
    {"symbol": "VINATIORGA", "name": "Vinati Organics", "sector": "Chemicals", "industry": "ATBS & Specialty Monomers", "cap": "MID", "price": 1780.00},
    {"symbol": "AARTIIND", "name": "Aarti Industries", "sector": "Chemicals", "industry": "Benzene Derivatives", "cap": "MID", "price": 480.00},
    {"symbol": "CESC", "name": "CESC Limited", "sector": "Power", "industry": "Power Generation & Distribution", "cap": "MID", "price": 175.00},
    {"symbol": "NLCINDIA", "name": "NLC India", "sector": "Power", "industry": "Lignite Mining & Power", "cap": "MID", "price": 245.00},
    {"symbol": "SJVN", "name": "SJVN Limited", "sector": "Power", "industry": "Hydro & Solar Power", "cap": "MID", "price": 115.00},
    {"symbol": "CASTROLIND", "name": "Castrol India", "sector": "Energy", "industry": "Automotive Lubricants", "cap": "MID", "price": 215.00},
    {"symbol": "MRPL", "name": "Mangalore Refinery", "sector": "Energy", "industry": "Petroleum Refining", "cap": "MID", "price": 158.00},
    {"symbol": "OIL", "name": "Oil India Limited", "sector": "Energy", "industry": "Upstream Oil & Gas", "cap": "MID", "price": 490.00},
    {"symbol": "GSPL", "name": "Gujarat State Petronet", "sector": "Energy", "industry": "Natural Gas Pipelines", "cap": "MID", "price": 380.00},
    {"symbol": "IGL", "name": "Indraprastha Gas", "sector": "Energy", "industry": "City Gas Distribution (NCR)", "cap": "MID", "price": 395.00},
    {"symbol": "MGL", "name": "Mahanagar Gas", "sector": "Energy", "industry": "City Gas Distribution (Mumbai)", "cap": "MID", "price": 1640.00},
    {"symbol": "CENTURYTEX", "name": "Century Textiles (Birla)", "sector": "Realty", "industry": "Real Estate & Pulp", "cap": "MID", "price": 2720.00},
    {"symbol": "BRIGADE", "name": "Brigade Enterprises", "sector": "Realty", "industry": "Residential & Tech Parks", "cap": "MID", "price": 1280.00},
    {"symbol": "SOBHA", "name": "Sobha Limited", "sector": "Realty", "industry": "Contractual & Residential", "cap": "MID", "price": 1850.00},
    {"symbol": "SUNTECK", "name": "Sunteck Realty", "sector": "Realty", "industry": "Luxury Real Estate", "cap": "MID", "price": 540.00},
    {"symbol": "MAHLIFE", "name": "Mahindra Lifespaces", "sector": "Realty", "industry": "Industrial Clusters & Homes", "cap": "MID", "price": 520.00},
    {"symbol": "BLUEDART", "name": "Blue Dart Express", "sector": "Services", "industry": "Air Express Logistics", "cap": "MID", "price": 7850.00},
    {"symbol": "ALLCARGO", "name": "Allcargo Logistics", "sector": "Services", "industry": "Multimodal Logistics", "cap": "MID", "price": 62.00},
    {"symbol": "AEGISLOG", "name": "Aegis Logistics", "sector": "Services", "industry": "LPG & Liquid Terminals", "cap": "MID", "price": 820.00},
    {"symbol": "MAHLOG", "name": "Mahindra Logistics", "sector": "Services", "industry": "3PL Supply Chain", "cap": "MID", "price": 385.00},
    {"symbol": "LEMONTREE", "name": "Lemon Tree Hotels", "sector": "Consumer Services", "industry": "Mid-priced Hotel Chain", "cap": "MID", "price": 128.00},
    {"symbol": "CHALET", "name": "Chalet Hotels", "sector": "Consumer Services", "industry": "High-end Business Hotels", "cap": "MID", "price": 840.00},
    {"symbol": "PVRINOX", "name": "PVR INOX Limited", "sector": "Consumer Services", "industry": "Multiplex Film Exhibition", "cap": "MID", "price": 1420.00},
    {"symbol": "RBLBANK", "name": "RBL Bank Limited", "sector": "Financial Services", "industry": "Private Sector Bank", "cap": "MID", "price": 168.00},
    {"symbol": "KARURVYSYA", "name": "Karur Vysya Bank", "sector": "Financial Services", "industry": "Private Sector Bank", "cap": "MID", "price": 218.00},
    {"symbol": "CITYUNIONB", "name": "City Union Bank", "sector": "Financial Services", "industry": "Private Sector Bank", "cap": "MID", "price": 164.00},
    {"symbol": "CUB", "name": "CreditAccess Grameen", "sector": "Financial Services", "industry": "Microfinance NBFC", "cap": "MID", "price": 1150.00},
    {"symbol": "MANAPPURAM", "name": "Manappuram Finance", "sector": "Financial Services", "industry": "Gold Loan NBFC", "cap": "MID", "price": 168.00},
    {"symbol": "IIFL", "name": "IIFL Finance", "sector": "Financial Services", "industry": "Retail Lending NBFC", "cap": "MID", "price": 420.00},
    {"symbol": "CHOLAHLDNG", "name": "Cholamandalam Financial", "sector": "Financial Services", "industry": "Holding Company", "cap": "MID", "price": 1540.00},
    {"symbol": "ABCAPITAL", "name": "Aditya Birla Capital", "sector": "Financial Services", "industry": "Financial Services Conglomerate", "cap": "MID", "price": 215.00},
    {"symbol": "CREDITACC", "name": "CreditAccess Grameen", "sector": "Financial Services", "industry": "Microfinance", "cap": "MID", "price": 1180.00},
    {"symbol": "FINPIPE", "name": "Finolex Industries", "sector": "Capital Goods", "industry": "PVC Pipes & Resin", "cap": "MID", "price": 285.00},
    {"symbol": "APLAPOLLO", "name": "APL Apollo Tubes", "sector": "Capital Goods", "industry": "Structural Steel Tubes", "cap": "MID", "price": 1480.00},
    {"symbol": "SUPREMEIND", "name": "Supreme Industries", "sector": "Capital Goods", "industry": "Plastic Piping & Moulded", "cap": "MID", "price": 4650.00},
    {"symbol": "CARBORUNIV", "name": "Carborundum Universal", "sector": "Capital Goods", "industry": "Abrasives & Ceramics", "cap": "MID", "price": 1420.00},
    {"symbol": "GRINDWELL", "name": "Grindwell Norton", "sector": "Capital Goods", "industry": "Abrasives", "cap": "MID", "price": 2240.00},
    {"symbol": "TIMKEN", "name": "Timken India", "sector": "Capital Goods", "industry": "Tapered Roller Bearings", "cap": "MID", "price": 3450.00},
    {"symbol": "SKFINDIA", "name": "SKF India Limited", "sector": "Capital Goods", "industry": "Bearings & Seals", "cap": "MID", "price": 4850.00},
    {"symbol": "SCHAEFFLER", "name": "Schaeffler India", "sector": "Capital Goods", "industry": "Ball & Roller Bearings", "cap": "MID", "price": 3820.00},
    {"symbol": "AIAENG", "name": "AIA Engineering", "sector": "Capital Goods", "industry": "High Chrome Mill Internals", "cap": "MID", "price": 4120.00},
    {"symbol": "CENTRALBK", "name": "Central Bank of India", "sector": "Financial Services", "industry": "Public Sector Bank", "cap": "MID", "price": 54.00},
    {"symbol": "IOB", "name": "Indian Overseas Bank", "sector": "Financial Services", "industry": "Public Sector Bank", "cap": "MID", "price": 51.00},
    {"symbol": "UCOBANK", "name": "UCO Bank", "sector": "Financial Services", "industry": "Public Sector Bank", "cap": "MID", "price": 42.00},
    {"symbol": "MAHABANK", "name": "Bank of Maharashtra", "sector": "Financial Services", "industry": "Public Sector Bank", "cap": "MID", "price": 56.00},
    {"symbol": "PSB", "name": "Punjab & Sind Bank", "sector": "Financial Services", "industry": "Public Sector Bank", "cap": "MID", "price": 48.00},
    {"symbol": "JKLAKSHMI", "name": "JK Lakshmi Cement", "sector": "Materials", "industry": "Cement", "cap": "MID", "price": 780.00},
    {"symbol": "JKCEMENT", "name": "JK Cement Limited", "sector": "Materials", "industry": "Grey & White Cement", "cap": "MID", "price": 4250.00},
    {"symbol": "DALBHARAT", "name": "Dalmia Bharat", "sector": "Materials", "industry": "Cement", "cap": "MID", "price": 1820.00},
    {"symbol": "STARCEMENT", "name": "Star Cement", "sector": "Materials", "industry": "North-East Cement", "cap": "MID", "price": 205.00},
    {"symbol": "HEIDELBERG", "name": "Heidelberg Cement India", "sector": "Materials", "industry": "Cement", "cap": "MID", "price": 218.00},
    {"symbol": "PRSMJOHNSN", "name": "Prism Johnson", "sector": "Materials", "industry": "Cement & Tiles", "cap": "MID", "price": 165.00},
    {"symbol": "KAJARIACER", "name": "Kajaria Ceramics", "sector": "Consumer Durables", "industry": "Ceramic Wall & Floor Tiles", "cap": "MID", "price": 1240.00},
    {"symbol": "CERA", "name": "Cera Sanitaryware", "sector": "Consumer Durables", "industry": "Sanitaryware & Faucets", "cap": "MID", "price": 7850.00},
    {"symbol": "CENTURYPLY", "name": "Century Plyboards", "sector": "Consumer Durables", "industry": "Plywood & Laminates", "cap": "MID", "price": 780.00},
    {"symbol": "GREENPANEL", "name": "Greenpanel Industries", "sector": "Consumer Durables", "industry": "MDF & Wood Panels", "cap": "MID", "price": 340.00},
    {"symbol": "AMBER", "name": "Amber Enterprises", "sector": "Consumer Durables", "industry": "HVAC OEM Solutions", "cap": "MID", "price": 5850.00},
    {"symbol": "SYRMA", "name": "Syrma SGS Technology", "sector": "Consumer Durables", "industry": "Electronics Manufacturing", "cap": "MID", "price": 480.00},
    {"symbol": "KAYNES", "name": "Kaynes Technology", "sector": "Consumer Durables", "industry": "IoT & EMS Solutions", "cap": "MID", "price": 5450.00},
    {"symbol": "CYIENT", "name": "Cyient Limited", "sector": "Information Technology", "industry": "Engineering & Technology", "cap": "MID", "price": 1780.00},
    {"symbol": "ZENSARTECH", "name": "Zensar Technologies", "sector": "Information Technology", "industry": "Experience & Tech Services", "cap": "MID", "price": 720.00},
    {"symbol": "BSOFT", "name": "Birlasoft Limited", "sector": "Information Technology", "industry": "Enterprise Cloud Services", "cap": "MID", "price": 610.00},
    {"symbol": "SONATSOFTW", "name": "Sonata Software", "sector": "Information Technology", "industry": "Modernization Engineering", "cap": "MID", "price": 640.00},
    {"symbol": "LATENTVIEW", "name": "Latent View Analytics", "sector": "Information Technology", "industry": "Data & AI Consulting", "cap": "MID", "price": 490.00},
    {"symbol": "HAPPSTMNDS", "name": "Happiest Minds Tech", "sector": "Information Technology", "industry": "Born Digital IT Solutions", "cap": "MID", "price": 780.00},
    {"symbol": "INTELLECT", "name": "Intellect Design Arena", "sector": "Information Technology", "industry": "FinTech Products & eGov", "cap": "MID", "price": 740.00},
    {"symbol": "MASTEK", "name": "Mastek Limited", "sector": "Information Technology", "industry": "Digital Commerce & Cloud", "cap": "MID", "price": 2850.00},
    {"symbol": "TANLA", "name": "Tanla Platforms", "sector": "Information Technology", "industry": "CPaaS & Blockchain Messaging", "cap": "MID", "price": 740.00},
    {"symbol": "ROUTE", "name": "Route Mobile", "sector": "Information Technology", "industry": "Omnichannel Messaging", "cap": "MID", "price": 1540.00},
]


class Command(BaseCommand):
    help = "Seeds the complete NIFTY 250 universe with 250-day candles, indicators, and fundamentals."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force recreation of candles and recalculation of all indicators.",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        self.stdout.write(f"Seeding NIFTY 250 universe ({len(NIFTY_250_STOCKS)} stocks, force={force})...")

        with transaction.atomic():
            nse, _ = Exchange.objects.get_or_create(
                code="NSE",
                defaults={"name": "National Stock Exchange of India", "country": "India", "currency": "INR"},
            )
            bse, _ = Exchange.objects.get_or_create(
                code="BSE",
                defaults={"name": "Bombay Stock Exchange", "country": "India", "currency": "INR"},
            )

        now = timezone.now()

        # Generate 250 trading day dates (excluding weekends) backwards from today
        trading_dates = []
        d = 0
        while len(trading_dates) < 250:
            day_date = (now - timedelta(days=d)).date()
            if day_date.weekday() not in (5, 6):
                trading_dates.append(day_date)
            d += 1
        trading_dates.reverse()  # Oldest to newest (today)

        created_instruments = 0
        total_candles_created = 0

        for idx, item in enumerate(NIFTY_250_STOCKS, 1):
            symbol = item["symbol"]
            target_p = item["price"]
            cap = item["cap"]
            sector = item["sector"]
            industry = item["industry"]
            name = item["name"]

            # 1. Instrument Registration
            default_isin = f"INE{abs(hash(symbol)) % 1000000000:09d}"
            inst = Instrument.objects.filter(display_name=symbol).first()
            if not inst:
                inst = Instrument.objects.filter(isin=default_isin).first()
            if not inst:
                inst = Instrument.objects.create(
                    isin=default_isin,
                    display_name=name,
                    legal_name=f"{name} Limited" if not name.endswith("Limited") else name,
                    sector=sector,
                    industry=industry,
                    market_cap_category=cap,
                )
                created_instruments += 1
            else:
                inst.market_cap_category = cap
                inst.sector = sector
                inst.industry = industry
                inst.save()

            # 2. Exchange Listing (NSE Primary)
            listing, _ = ExchangeListing.objects.get_or_create(
                exchange=nse,
                symbol=symbol,
                defaults={
                    "instrument": inst,
                    "trading_symbol": f"{symbol}-EQ",
                    "series_or_group": "EQ",
                    "is_primary": True,
                    "is_tradeable": True,
                },
            )
            if listing.instrument_id != inst.id:
                listing.instrument = inst
                listing.save()

            # 3. Candles Generation
            existing_count = HistoricalCandle.objects.filter(listing=listing, interval="1d").count()
            if force or existing_count < 200:
                random.seed(42 + hash(symbol) % 1000)

                # Assign trend characteristics:
                # 45% Bullish, 35% Neutral/Consolidating, 20% Bearish
                h = abs(hash(symbol)) % 100
                if h < 45:
                    start_p = target_p * random.uniform(0.68, 0.78)  # +28% to +47% uptrend
                elif h < 80:
                    start_p = target_p * random.uniform(0.92, 1.05)  # Sideways / oscillating
                else:
                    start_p = target_p * random.uniform(1.22, 1.38)  # -18% to -28% downtrend

                N = len(trading_dates)
                daily_drift = (target_p / start_p) ** (1.0 / N) - 1.0

                current_p = start_p
                simulated_closes = []
                for _ in range(N):
                    noise = random.uniform(-0.016, 0.016)
                    current_p = current_p * (1.0 + daily_drift + noise)
                    simulated_closes.append(current_p)

                # Scale so terminal candle close precisely equals target_p
                scale = target_p / simulated_closes[-1]
                scaled_closes = [round(p * scale, 2) for p in simulated_closes]
                scaled_closes[-1] = round(target_p, 2)

                HistoricalCandle.objects.filter(listing=listing, interval="1d").delete()

                candles_to_create = []
                last_open = scaled_closes[0]
                last_high = scaled_closes[0]
                last_low = scaled_closes[0]
                last_close = scaled_closes[0]
                last_prev_close = scaled_closes[0]
                last_vol = 1000000

                for i, day_date in enumerate(trading_dates):
                    ts = datetime.combine(day_date, datetime.min.time(), tzinfo=UTC)
                    close_p = scaled_closes[i]
                    prev_p = scaled_closes[i - 1] if i > 0 else close_p
                    open_p = round(prev_p * (1 + random.uniform(-0.003, 0.003)), 2)
                    high_p = round(max(open_p, close_p) * (1 + random.uniform(0.002, 0.012)), 2)
                    low_p = round(min(open_p, close_p) * (1 - random.uniform(0.002, 0.012)), 2)
                    vol = random.randint(300000, 3500000)

                    candles_to_create.append(
                        HistoricalCandle(
                            listing=listing,
                            timestamp=ts,
                            interval="1d",
                            open=Decimal(str(open_p)),
                            high=Decimal(str(high_p)),
                            low=Decimal(str(low_p)),
                            close=Decimal(str(close_p)),
                            volume=vol,
                            adjusted_close=Decimal(str(close_p)),
                            source_provider="SEEDED",
                        )
                    )
                    last_open = open_p
                    last_high = high_p
                    last_low = low_p
                    last_close = close_p
                    last_prev_close = prev_p
                    last_vol = vol

                HistoricalCandle.objects.bulk_create(candles_to_create)
                total_candles_created += len(candles_to_create)

                # Keep MarketQuote updated
                existing_quote = MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first()
                if existing_quote:
                    existing_quote.price = Decimal(str(last_close))
                    existing_quote.open = Decimal(str(last_open))
                    existing_quote.high = Decimal(str(last_high))
                    existing_quote.low = Decimal(str(last_low))
                    existing_quote.close = Decimal(str(last_close))
                    existing_quote.previous_close = Decimal(str(last_prev_close))
                    existing_quote.change = Decimal(str(round(last_close - last_prev_close, 2)))
                    existing_quote.change_percent = (
                        Decimal(str(round((last_close - last_prev_close) / last_prev_close * 100, 2)))
                        if last_prev_close
                        else Decimal("0.0")
                    )
                    existing_quote.volume = last_vol
                    existing_quote.source_timestamp = now
                    existing_quote.retrieved_at = now
                    existing_quote.save()
                else:
                    MarketQuote.objects.create(
                        listing=listing,
                        source_provider="SEEDED",
                        source_type="DELAYED",
                        freshness_status="FRESH",
                        source_timestamp=now,
                        retrieved_at=now,
                        price=Decimal(str(last_close)),
                        open=Decimal(str(last_open)),
                        high=Decimal(str(last_high)),
                        low=Decimal(str(last_low)),
                        close=Decimal(str(last_close)),
                        previous_close=Decimal(str(last_prev_close)),
                        change=Decimal(str(round(last_close - last_prev_close, 2))),
                        change_percent=(
                            Decimal(str(round((last_close - last_prev_close) / last_prev_close * 100, 2)))
                            if last_prev_close
                            else Decimal("0.0")
                        ),
                        volume=last_vol,
                        configured_delay_minutes=15,
                    )

            # 4. Compute Technical Indicators
            all_candles = list(HistoricalCandle.objects.filter(listing=listing, interval="1d").order_by("timestamp"))
            TechnicalIndicatorCalculator.compute_and_store_snapshots(listing, all_candles)

            # 5. Populate Realistic Fundamental Snapshot
            random.seed(100 + hash(symbol) % 1000)
            sector_pe_map = {
                "Financial Services": 16.5,
                "Information Technology": 28.5,
                "Energy": 14.0,
                "Consumer Goods": 38.0,
                "Automobile": 22.0,
                "Healthcare": 32.0,
                "Metals & Mining": 12.0,
                "Capital Goods": 35.0,
                "Power": 16.0,
                "Chemicals": 29.0,
                "Realty": 26.0,
                "Services": 30.0,
            }
            sec_pe = sector_pe_map.get(sector, 24.0)
            pe_val = round(sec_pe * random.uniform(0.75, 1.35), 1)
            roe_val = round(random.uniform(9.5, 34.0), 1)
            roce_val = round(roe_val * random.uniform(0.9, 1.25), 1)
            de_val = 0.0 if sector == "Information Technology" else (
                round(random.uniform(0.8, 1.4), 2) if sector == "Financial Services" else round(random.uniform(0.05, 0.75), 2)
            )

            fund_data = {
                "pe_ratio": pe_val,
                "pb_ratio": round(pe_val * (roe_val / 100.0) * random.uniform(0.8, 1.2), 2),
                "ps_ratio": round(random.uniform(1.2, 5.8), 2),
                "ev_to_ebitda": round(pe_val * 0.65, 1),
                "dividend_yield": round(random.uniform(0.3, 3.8), 2),
                "sector_pe": sec_pe,
                "roe": roe_val,
                "roce": roce_val,
                "operating_margin": round(random.uniform(11.0, 32.0), 1),
                "net_profit_margin": round(random.uniform(6.5, 22.0), 1),
                "eps": round(target_p / pe_val, 2),
                "debt_to_equity": de_val,
                "current_ratio": round(random.uniform(1.1, 2.5), 2),
                "interest_coverage_ratio": round(random.uniform(4.5, 45.0), 1),
                "free_cash_flow": round(random.uniform(500.0, 18000.0), 1),
                "revenue_growth_yoy": round(random.uniform(6.0, 24.0), 1),
                "profit_growth_yoy": round(random.uniform(8.0, 28.0), 1),
                "promoter_holding": round(random.uniform(35.0, 74.0), 1),
                "fii_holding": round(random.uniform(10.0, 38.0), 1),
                "dii_holding": round(random.uniform(8.0, 28.0), 1),
                "public_holding": round(random.uniform(6.0, 22.0), 1),
            }
            FundamentalAnalyzer.evaluate_instrument(inst, fund_data)

            if idx % 25 == 0 or idx == len(NIFTY_250_STOCKS):
                self.stdout.write(f"Processed {idx}/{len(NIFTY_250_STOCKS)} stocks...")

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully seeded NIFTY 250 universe! ({created_instruments} new instruments, "
                f"{total_candles_created} historical candles)."
            )
        )
