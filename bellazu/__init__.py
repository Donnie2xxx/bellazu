"""BellaZu: free real-estate analysis core.

Public API (returns plain JSON-serializable dicts):
    analyze_property(address, options=None) -> dict
    scan_arbitrage(town, options=None) -> dict
Rendering lives in bellazu.render (kept separate so a web app can reuse the core).
"""
from .core import analyze_property, scan_arbitrage  # noqa: F401
__version__ = "0.1.0"
