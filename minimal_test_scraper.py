#!/usr/bin/env python3

from scraper import ShortMaxScraper
from selenium.webdriver.common.by import By
import logging
import time

def run_minimal_test_scraper():
    """
    Minimal test scraper to verify deduplication fix
    Focus only on homepage extraction to test deduplication logic
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    scraper = ShortMaxScraper()
    scraper.setup_driver()
    
    all_works = []
    
    try:
        print('=== MINIMAL TEST SCRAPER ===')
        print('Testing improved deduplication logic...')
        
        print('\n--- Phase 1: Single Homepage Extraction ---')
        scraper.driver.get('https://shortmax.app/tabbar/home')
        time.sleep(8)
        
        for i in range(30):
            scraper.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
        
        homepage_works = scraper.extract_work_data_from_elements('Homepage Test')
        all_works.extend(homepage_works)
        print(f'Extracted {len(homepage_works)} works from homepage')
        
        print('\n--- Phase 2: Test Deduplication ---')
        print(f'Total works before deduplication: {len(all_works)}')
        
        scraper.all_works_data = all_works
        scraper.remove_duplicates()
        print(f'Unique works after improved deduplication: {len(scraper.all_works_data)}')
        
        if len(all_works) > 0:
            retention_rate = (len(scraper.all_works_data) / len(all_works)) * 100
            print(f'Deduplication retention rate: {retention_rate:.1f}%')
        
        print('\n--- Phase 3: Export and Analysis ---')
        csv_file = scraper.export_to_csv()
        print(f'Results exported to: {csv_file}')
        
        print('\n=== MINIMAL TEST RESULTS ===')
        print(f'Total unique works found: {len(scraper.all_works_data)}')
        
        sorted_works = sorted(scraper.all_works_data, 
                            key=lambda x: scraper.parse_view_count_to_number(x['view_count']), 
                            reverse=True)
        
        print('\nTop 15 works by view count:')
        for i, work in enumerate(sorted_works[:15]):
            print(f'{i+1}. "{work["title"]}" - {work["view_count"]} views')
        
        high_view_works = [w for w in scraper.all_works_data if scraper.parse_view_count_to_number(w['view_count']) > 100000]
        medium_view_works = [w for w in scraper.all_works_data if 10000 < scraper.parse_view_count_to_number(w['view_count']) <= 100000]
        low_view_works = [w for w in scraper.all_works_data if scraper.parse_view_count_to_number(w['view_count']) <= 10000]
        
        print(f'\nView count analysis:')
        print(f'High view count (>100K): {len(high_view_works)} works')
        print(f'Medium view count (10K-100K): {len(medium_view_works)} works')
        print(f'Low view count (≤10K): {len(low_view_works)} works')
        
        if len(scraper.all_works_data) >= 200:
            print(f'\n🟢 GOOD: Found {len(scraper.all_works_data)} unique works from single homepage')
            print('Deduplication logic appears to be working better!')
        elif len(scraper.all_works_data) >= 100:
            print(f'\n🟡 MODERATE: Found {len(scraper.all_works_data)} unique works from single homepage')
            print('Some improvement in deduplication')
        else:
            print(f'\n🔴 POOR: Found {len(scraper.all_works_data)} unique works from single homepage')
            print('Deduplication may still be too aggressive')
        
        return csv_file
        
    finally:
        scraper.driver.quit()

if __name__ == "__main__":
    run_minimal_test_scraper()
