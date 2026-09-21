# -*- coding: utf-8 -*-
"""
Temporary single search test for Google Ads lead extraction.
Delete this file after the test.
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scraper.sniper.headless_extract import search_one

async def main():
    query = 'courtier pret immobilier Paris'
    port = 9701
    print(f'Running single search for: {query}')
    result = await search_one(query, port)
    print('Result:', result)

if __name__ == '__main__':
    asyncio.run(main())
