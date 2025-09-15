# Self‑Hosted Search Engine

This repository contains a simple search engine that you can run
entirely on your own machine.  It consists of three separate
components:

1. **Crawler** – built with Scrapy.  It traverses websites starting
   from a list of seed URLs or domains, downloads each page, and
   extracts the title and body text.  The extracted documents are
   written to a newline‑delimited JSON file under `data/pages.jsonl`.
2. **Indexer** – a standalone Python script that reads the JSON
   document file and builds an inverted index using the Whoosh
   library.  The resulting index is stored in the `index/`
   directory.
3. **Search UI** – a small Flask web application that presents a
   search box and displays results from the Whoosh index.  It
   supports full‑text search across both titles and page content
   with BM25 ranking and snippet highlighting.

The code here follows the architecture described in the attached
research report: an **offline pipeline** (crawling and indexing)
and an **online pipeline** (query processing and ranking)【10†L72-L80】.
Everything runs locally without sending data to any third‑party
service, preserving your privacy and making the system fully
self‑hosted.

## Quick start

1. **Install dependencies**  
   We recommend using a virtual environment.  From the project root:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt

   # Install Playwright browsers once:
   python -m playwright install
   ```

2. **Crawl some websites**  
   The crawler can operate in two modes:

   - **Seed mode** – specify one or more starting URLs.  The spider
     will crawl pages under those domains.  For example:

     ```bash
     cd crawler
     scrapy crawl site -a start_urls="https://example.com,https://docs.python.org" \
                      -a allow="example.com|docs.python.org" \
                      -a max_pages=100
     ```

   - **Domain list mode** – provide a text file containing domain
     names (one per line) and the `phonebook` spider will fetch only
     the home page of each site.  This is useful when you have a
     large list of websites and want to build a broad “phone book”
     style index.  For example:

     ```bash
     cd crawler
     scrapy crawl phonebook -a domain_file="domains.txt"
     ```

   The crawler writes each page to `data/pages.jsonl`.  Feel free to
   run multiple crawl commands to accumulate a larger corpus.

3. **Build the index**

   Once you have some documents in `data/pages.jsonl`, run:

   ```bash
   python index_build.py
   ```

   This will create (or update) a Whoosh index in the `index/`
   directory.  You can re-run this whenever new pages are crawled to
   keep the index fresh.

4. **Run the search UI**

   To start the Flask app, execute:

   ```bash
   cd app
   python main.py
   ```

   Then open `http://localhost:5000` in your browser.  Enter a
   search query to see matching pages with titles and snippets.

5. **Command‑line search**

   A simple CLI utility is provided for quick searches without the
   web UI:

   ```bash
   python cli_search.py "your search terms"
   ```

## Notes on scalability

This project is designed for personal use.  Crawling the entire web
is an enormous undertaking: there are billions of pages on the
internet【21†L90-L97】, and indexing them requires terabytes of storage
and significant compute.  On a single laptop you should start with a
modest corpus (tens of thousands or perhaps millions of pages).  The
`phonebook` spider lets you create a broad directory by fetching only
home pages, and you can gradually expand the crawl depth and number
of pages per domain as resources allow.

If your corpus grows too large for Whoosh to handle, consider using a
more scalable engine such as MeiliSearch or Apache Lucene, both of
which can index hundreds of millions of documents more efficiently【17†L281-L289】.
