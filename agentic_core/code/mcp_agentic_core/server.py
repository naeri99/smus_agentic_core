"""
server.py
"""

import yfinance as yf
import numpy as np
from datetime import datetime, timedelta
from mcp.server.fastmcp import FastMCP

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(host="0.0.0.0", stateless_http=True)

@mcp.tool()
def add(a: float, b: float) -> float:
    """두 숫자를 더합니다"""
    return a + b

@mcp.tool()
def multiply(a: float, b: float) -> float:
    """두 숫자를 곱합니다"""
    return a * b

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
