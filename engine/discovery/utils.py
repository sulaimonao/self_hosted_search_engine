from __future__ import annotations

from typing import List, TypedDict

# This is a placeholder for the actual google_search tool.
# The agent framework will handle the injection of the tool.
def google_search(query: str, limit: int = 10) -> List[TypedDict("SearchResult", {"link": str, "title": str, "snippet": str})]:
    """Perform a Google search and return the results."""
    # In a real environment, this would call the google_search tool.
    # For testing, we return dummy data.
    return [
        {
            "link": f"https://example.com/{query.replace(' ', '_')}_{i}",
            "title": f"Title for {query} {i}",
            "snippet": f"Snippet for {query} {i}",
        }
        for i in range(limit)
    ]
