import json
from pathlib import Path

class JsonlWriterPipeline:
    """
    Pipeline that writes each scraped item to a newline‑delimited JSON
    file.  The file lives in the top‑level `data/` directory.  The
    pipeline appends to the file so multiple crawl runs accumulate
    into a single dataset.
    """

    def open_spider(self, spider):
        # Ensure the data directory exists
        data_dir = Path(__file__).resolve().parents[2] / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.fp = open(data_dir / "pages.jsonl", "a", encoding="utf-8")

    def close_spider(self, spider):
        if hasattr(self, "fp") and self.fp:
            self.fp.close()

    def process_item(self, item, spider):
        # Convert Scrapy Item to plain dict and write as JSON line.
        self.fp.write(json.dumps(dict(item), ensure_ascii=False) + "\n")
        return item