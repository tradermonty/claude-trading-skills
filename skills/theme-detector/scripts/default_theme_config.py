"""Default inline theme configuration (fallback when YAML is unavailable).

This module holds DEFAULT_THEMES_CONFIG and ETF_CATALOG constants extracted
from theme_detector.py to avoid circular imports between theme_detector.py
and config_loader.py.
"""

from typing import Dict

DEFAULT_THEMES_CONFIG: Dict = {
    "cross_sector_min_matches": 2,
    "vertical_min_industries": 3,
    "cross_sector": [
        {
            "theme_name": "AI & Semiconductors",
            "matching_keywords": [
                "Semiconductors",
                "Semiconductor Equipment & Materials",
                "Software - Application",
                "Software - Infrastructure",
                "Information Technology Services",
                "Computer Hardware",
                "Electronic Components",
            ],
            "proxy_etfs": ["SMH", "SOXX", "AIQ", "BOTZ"],
            "static_stocks": [
                "NVDA", "AVGO", "AMD", "INTC", "QCOM",
                "MRVL", "AMAT", "LRCX", "KLAC", "TSM",
            ],
        },
        {
            "theme_name": "Clean Energy & EV",
            "matching_keywords": [
                "Solar",
                "Utilities - Renewable",
                "Auto Manufacturers",
                "Electrical Equipment & Parts",
                "Specialty Chemicals",
            ],
            "proxy_etfs": ["ICLN", "QCLN", "TAN", "LIT"],
            "static_stocks": [
                "ENPH", "SEDG", "FSLR", "RUN", "TSLA",
                "RIVN", "ALB", "PLUG", "BE", "NEE",
            ],
        },
        {
            "theme_name": "Cybersecurity",
            "matching_keywords": [
                "Software - Infrastructure",
                "Software - Application",
                "Information Technology Services",
            ],
            "proxy_etfs": ["CIBR", "HACK", "BUG"],
            "static_stocks": [
                "CRWD", "PANW", "FTNT", "ZS", "S",
                "OKTA", "NET", "CYBR", "QLYS", "RPD",
            ],
        },
        {
            "theme_name": "Cloud Computing & SaaS",
            "matching_keywords": [
                "Software - Application",
                "Software - Infrastructure",
                "Information Technology Services",
            ],
            "proxy_etfs": ["SKYY", "WCLD", "CLOU"],
            "static_stocks": [
                "CRM", "NOW", "SNOW", "DDOG", "MDB",
                "NET", "ZS", "HUBS", "WDAY", "TEAM",
            ],
        },
        {
            "theme_name": "Biotech & Genomics",
            "matching_keywords": [
                "Biotechnology",
                "Drug Manufacturers - General",
                "Drug Manufacturers - Specialty & Generic",
                "Diagnostics & Research",
            ],
            "proxy_etfs": ["XBI", "IBB", "ARKG"],
            "static_stocks": [
                "AMGN", "GILD", "VRTX", "REGN", "MRNA",
                "BIIB", "ILMN", "SGEN", "ALNY", "BMRN",
            ],
        },
        {
            "theme_name": "Infrastructure & Construction",
            "matching_keywords": [
                "Engineering & Construction",
                "Building Products & Equipment",
                "Building Materials",
                "Specialty Industrial Machinery",
                "Farm & Heavy Construction Machinery",
                "Infrastructure Operations",
            ],
            "proxy_etfs": ["PAVE", "IFRA"],
            "static_stocks": [
                "CAT", "DE", "VMC", "MLM", "URI",
                "PWR", "EME", "J", "ACM", "FAST",
            ],
        },
        {
            "theme_name": "Gold & Precious Metals",
            "matching_keywords": [
                "Gold",
                "Silver",
                "Other Precious Metals & Mining",
            ],
            "proxy_etfs": ["GDX", "GDXJ", "SLV", "GLD"],
            "static_stocks": [
                "NEM", "GOLD", "AEM", "FNV", "WPM",
                "RGLD", "KGC", "AGI", "HL", "PAAS",
            ],
        },
        {
            "theme_name": "Oil & Gas (Energy)",
            "matching_keywords": [
                "Oil & Gas E&P",
                "Oil & Gas Equipment & Services",
                "Oil & Gas Integrated",
                "Oil & Gas Midstream",
                "Oil & Gas Refining & Marketing",
                "Oil & Gas Drilling",
            ],
            "proxy_etfs": ["XLE", "XOP", "OIH"],
            "static_stocks": [
                "XOM", "CVX", "COP", "EOG", "SLB",
                "PXD", "MPC", "PSX", "OXY", "DVN",
            ],
        },
        {
            "theme_name": "Financial Services & Banks",
            "matching_keywords": [
                "Banks - Diversified",
                "Banks - Regional",
                "Capital Markets",
                "Insurance - Diversified",
                "Financial Data & Stock Exchanges",
                "Asset Management",
            ],
            "proxy_etfs": ["XLF", "KBE", "KRE"],
            "static_stocks": [
                "JPM", "BAC", "GS", "MS", "WFC",
                "C", "BLK", "SCHW", "ICE", "CME",
            ],
        },
        {
            "theme_name": "Healthcare & Pharma",
            "matching_keywords": [
                "Drug Manufacturers - General",
                "Medical Devices",
                "Medical Instruments & Supplies",
                "Healthcare Plans",
                "Medical Care Facilities",
            ],
            "proxy_etfs": ["XLV", "IHI", "XBI"],
            "static_stocks": [
                "UNH", "JNJ", "LLY", "PFE", "ABT",
                "TMO", "DHR", "SYK", "ISRG", "MDT",
            ],
        },
        {
            "theme_name": "Defense & Aerospace",
            "matching_keywords": [
                "Aerospace & Defense",
                "Communication Equipment",
                "Scientific & Technical Instruments",
            ],
            "proxy_etfs": ["ITA", "PPA", "XAR"],
            "static_stocks": [
                "LMT", "RTX", "NOC", "GD", "BA",
                "LHX", "HII", "TDG", "HWM", "AXON",
            ],
        },
        {
            "theme_name": "Real Estate & REITs",
            "matching_keywords": [
                "REIT - Diversified",
                "REIT - Industrial",
                "REIT - Residential",
                "REIT - Retail",
                "REIT - Specialty",
                "REIT - Office",
                "Real Estate - Development",
                "Real Estate Services",
            ],
            "proxy_etfs": ["VNQ", "IYR", "XLRE"],
            "static_stocks": [
                "PLD", "AMT", "EQIX", "CCI", "SPG",
                "O", "WELL", "DLR", "PSA", "AVB",
            ],
        },
        {
            "theme_name": "Retail & Consumer",
            "matching_keywords": [
                "Internet Retail",
                "Specialty Retail",
                "Apparel Retail",
                "Discount Stores",
                "Home Improvement Retail",
                "Department Stores",
            ],
            "proxy_etfs": ["XRT", "XLY"],
            "static_stocks": [
                "AMZN", "HD", "LOW", "TJX", "COST",
                "WMT", "TGT", "ROST", "BURL", "LULU",
            ],
        },
        {
            "theme_name": "Crypto & Blockchain",
            "matching_keywords": [
                "Capital Markets",
                "Software - Infrastructure",
                "Financial Data & Stock Exchanges",
            ],
            "proxy_etfs": ["BITO", "BLOK", "BITQ"],
            "static_stocks": [
                "COIN", "MSTR", "MARA", "RIOT", "CLSK",
                "HUT", "BITF", "HIVE", "SQ", "PYPL",
            ],
        },
        {
            "theme_name": "Nuclear & Uranium",
            "matching_keywords": [
                "Uranium",
                "Utilities - Independent Power Producers",
                "Utilities - Regulated Electric",
            ],
            "proxy_etfs": ["URA", "URNM", "NLR"],
            "static_stocks": [
                "CCJ", "UEC", "NXE", "DNN", "LEU",
                "SMR", "UUUU", "URG", "OKLO", "VST",
            ],
        },
    ],
}

ETF_CATALOG: Dict[str, int] = {
    "AI & Semiconductors": 8,
    "Clean Energy & EV": 7,
    "Cybersecurity": 4,
    "Cloud Computing & SaaS": 4,
    "Biotech & Genomics": 5,
    "Infrastructure & Construction": 3,
    "Gold & Precious Metals": 4,
    "Oil & Gas (Energy)": 5,
    "Financial Services & Banks": 5,
    "Healthcare & Pharma": 5,
    "Defense & Aerospace": 5,
    "Real Estate & REITs": 4,
    "Retail & Consumer": 3,
    "Crypto & Blockchain": 4,
    "Nuclear & Uranium": 3,
}
