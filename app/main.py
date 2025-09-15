#!/usr/bin/env python3
"""
Flask web application for the self‑hosted search engine.

The app exposes a simple user interface to enter search queries and
display results with titles, URLs, and snippets.  It uses Whoosh to
search the prebuilt index.  To run:

    python main.py

Then visit http://localhost:5000 in your browser.
"""
from flask import Flask, render_template, request
from whoosh import index
from whoosh.qparser import MultifieldParser, OrGroup
from whoosh.highlight import HtmlFormatter

app = Flask(__name__)

# Load the index on startup.  If the index is missing, the app will
# fail to start; ensure you have run index_build.py.
ix = index.open_dir("../index")

@app.route("/")
def home():
    return render_template("base.html")

@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    page = int(request.args.get("page", 1))
    per_page = 10
    results = []
    total = 0
    if q:
        with ix.searcher() as s:
            parser = MultifieldParser(["title", "content"], ix.schema, group=OrGroup)
            try:
                query = parser.parse(q)
            except Exception:
                query = parser.parse("")  # fallback on parse error
            hits = s.search_page(query, page, pagelen=per_page)
            # Configure highlighting
            hits.fragmenter.charlimit = None
            hits.fragmenter.maxchars = 250
            hits.formatter = HtmlFormatter(tagname="mark")
            for h in hits:
                snippet = h.highlights("content") or ""
                results.append({
                    "title": h.get("title", "(untitled)"),
                    "url": h.get("url"),
                    "snippet": snippet,
                })
            total = hits.total
    return render_template("results.html", q=q, page=page, per_page=per_page,
                           results=results, total=total)

if __name__ == "__main__":
    app.run(debug=True, port=5000)