"""core package for OpenTrade Bot.

This file makes `core` a package so imports like `from core.portfolio import Portfolio`
work when running scripts from the project root or with Streamlit.
"""

__all__ = ["data_feed", "portfolio", "trader"]
