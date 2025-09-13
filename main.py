#!/usr/bin/env python3

import logging
import sys
import argparse
from datetime import datetime

from config import Config
from scraper import ShortMaxScraper

def setup_logging():
    logging.basicConfig(
        level=Config.LOG_LEVEL,
        format=Config.LOG_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(f'shortmax_scraper_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        ]
    )

def main():
    parser = argparse.ArgumentParser(description='ShortMax Comprehensive Web Scraper')
    parser.add_argument('--output', '-o', default='shortmax_works_data.csv', 
                       help='Output CSV filename (default: shortmax_works_data.csv)')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("ShortMax Comprehensive Scraper Starting")
    logger.info("=" * 60)
    logger.info(f"Target URL: {Config.BASE_URL}")
    logger.info(f"Output file: {args.output}")
    logger.info(f"Sections to scrape: {', '.join(Config.SECTIONS_TO_SCRAPE)}")
    logger.info(f"Categories to scrape: {', '.join(Config.CATEGORIES_TO_SCRAPE)}")
    
    try:
        scraper = ShortMaxScraper()
        csv_file = scraper.run_scraper()
        
        if csv_file:
            logger.info("=" * 60)
            logger.info("SCRAPING COMPLETED SUCCESSFULLY!")
            logger.info("=" * 60)
            logger.info(f"Data exported to: {csv_file}")
            logger.info(f"Total works scraped: {len(scraper.all_works_data)}")
            
            if scraper.all_works_data:
                logger.info("\nSample of scraped data:")
                for i, work in enumerate(scraper.all_works_data[:3]):
                    logger.info(f"  {i+1}. {work['title']} - {work['view_count']} views")
            
            return 0
        else:
            logger.error("Scraping failed - no data exported")
            return 1
            
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
