#!/usr/bin/env python3

from scraper import ShortMaxScraper
import logging

def process_collected_data():
    """
    Process the 938 works collected by systematic_comprehensive_scraper.py
    Apply improved deduplication and generate final results
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    scraper = ShortMaxScraper()
    
    import pandas as pd
    
    try:
        df = pd.read_csv('shortmax_works_data.csv')
        print(f'Loaded {len(df)} works from CSV')
        
        all_works = df.to_dict('records')
        
        print('\n=== PROCESSING COLLECTED DATA ===')
        print(f'Total works before deduplication: {len(all_works)}')
        
        scraper.all_works_data = all_works
        scraper.remove_duplicates()
        
        print(f'Unique works after improved deduplication: {len(scraper.all_works_data)}')
        
        if len(all_works) > 0:
            retention_rate = (len(scraper.all_works_data) / len(all_works)) * 100
            print(f'Deduplication retention rate: {retention_rate:.1f}%')
        
        csv_file = scraper.export_to_csv()
        print(f'Final results exported to: {csv_file}')
        
        print('\n=== FINAL COMPREHENSIVE RESULTS ===')
        print(f'Total unique works found: {len(scraper.all_works_data)}')
        
        sorted_works = sorted(scraper.all_works_data, 
                            key=lambda x: scraper.parse_view_count_to_number(x['view_count']), 
                            reverse=True)
        
        print('\nTop 25 works by view count:')
        for i, work in enumerate(sorted_works[:25]):
            print(f'{i+1}. "{work["title"]}" - {work["view_count"]} views - {work.get("section", "N/A")}')
        
        high_view_works = [w for w in scraper.all_works_data if scraper.parse_view_count_to_number(w['view_count']) > 100000]
        medium_view_works = [w for w in scraper.all_works_data if 10000 < scraper.parse_view_count_to_number(w['view_count']) <= 100000]
        low_view_works = [w for w in scraper.all_works_data if scraper.parse_view_count_to_number(w['view_count']) <= 10000]
        
        print(f'\nView count analysis:')
        print(f'High view count (>100K): {len(high_view_works)} works')
        print(f'Medium view count (10K-100K): {len(medium_view_works)} works')
        print(f'Low view count (≤10K): {len(low_view_works)} works')
        
        section_counts = {}
        for work in scraper.all_works_data:
            sec = work.get('section', 'Unknown')
            section_counts[sec] = section_counts.get(sec, 0) + 1
        
        print('\nSection distribution:')
        for sec, count in sorted(section_counts.items(), key=lambda x: x[1], reverse=True):
            print(f'{sec}: {count} works')
        
        tag_counts = {}
        for work in scraper.all_works_data:
            tags = work.get('tags', '')
            if tags:
                for tag in tags.split(','):
                    tag = tag.strip()
                    if tag:
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        print('\nTop tags:')
        for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f'{tag}: {count} works')
        
        if len(scraper.all_works_data) >= 800:
            print(f'\n🎉 SUCCESS: Found {len(scraper.all_works_data)} unique works (target: 800+)')
            print('✅ Successfully achieved comprehensive scraping target!')
        elif len(scraper.all_works_data) >= 600:
            print(f'\n🟢 EXCELLENT PROGRESS: Found {len(scraper.all_works_data)} unique works (target: 800+)')
            print('Very close to target, significant improvement!')
        elif len(scraper.all_works_data) >= 400:
            print(f'\n🟡 GOOD PROGRESS: Found {len(scraper.all_works_data)} unique works (target: 800+)')
            print('Substantial improvement over initial results')
        elif len(scraper.all_works_data) >= 200:
            print(f'\n🟠 MODERATE PROGRESS: Found {len(scraper.all_works_data)} unique works (target: 800+)')
            print('Good improvement with better deduplication')
        else:
            print(f'\n🔴 LIMITED PROGRESS: Found {len(scraper.all_works_data)} unique works (target: 800+)')
            print('Need to investigate additional content discovery methods')
        
        return csv_file
        
    except Exception as e:
        print(f'Error processing data: {e}')
        return None

if __name__ == "__main__":
    process_collected_data()
