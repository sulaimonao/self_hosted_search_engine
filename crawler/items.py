import scrapy

class PageItem(scrapy.Item):
    """
    Definition of a crawled page.  Only a few fields are stored to
    reduce disk usage during large crawls.
    """
    url = scrapy.Field()
    title = scrapy.Field()
    html = scrapy.Field()
    text = scrapy.Field()