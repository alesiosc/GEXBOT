"""Test TV paste in a clean process."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from gamma_scraper import paste_into_tv

test_data = [
    ("NQ", "NQ - Zulu Vol Lo 29635.54; Zulu Vol Hi 29775.61; Zulu OI Lo 29215.32; Zulu OI Hi 29815.63"),
    ("ES", "ES - Zulu Vol Lo 7462.61; Zulu Vol Hi 7497.88; Zulu OI Lo 7356.8; Zulu OI Hi 7507.96"),
]
paste_into_tv(test_data)
