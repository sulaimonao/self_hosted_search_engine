import scrapy


class PageItem(scrapy.Item):
    url = scrapy.Field()
    title = scrapy.Field()
    html = scrapy.Field()
    text = scrapy.Field()
    domain = scrapy.Field()
    fetched_at = scrapy.Field()
