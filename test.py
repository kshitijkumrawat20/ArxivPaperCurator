print('Hello, Lightning World!')
import asyncio
from datetime import datetime, timedelta

# Import our arXiv client
from src.services.arxiv.factory import make_arxiv_client

print("TESTING ARXIV API CLIENT")
print("=" * 40)

# Create client
arxiv_client = make_arxiv_client()
print(f"✓ Client created: {arxiv_client.base_url}")
print(f"   Rate limit: {arxiv_client.rate_limit_delay}s")
print(f"   Max results: {arxiv_client.max_results_per_query}")
print(f"   Category: {arxiv_client.search_category}")
print()