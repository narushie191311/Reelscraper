import logging
from typing import Dict, List

class Config:
    BASE_URL = "https://shortmax.app/tabbar/home"
    
    CHROME_OPTIONS = [
        "--headless",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1920,1080",
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ]
    
    WAIT_TIMEOUT = 10
    RETRY_ATTEMPTS = 3
    DELAY_BETWEEN_REQUESTS = 2
    
    SECTIONS_TO_SCRAPE = [
        "Premium Drama",
        "Most Popular", 
        "Most Trending",
        "Don't Miss Originals",
        "Hot Now",
        "New Drama Selection",
        "Original Series",
        "Popular Now"
    ]
    
    CATEGORIES_TO_SCRAPE = [
        "Historical",
        "Urban", 
        "High Fantasy",
        "Elite Families",
        "Werewolf",
        "Modern Love"
    ]
    
    CSV_COLUMNS = [
        "title",
        "view_count", 
        "synopsis",
        "section",
        "category",
        "tags",
        "episode_count",
        "detailed_description",
        "url",
        "scrape_timestamp"
    ]
    
    LOG_LEVEL = logging.INFO
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
