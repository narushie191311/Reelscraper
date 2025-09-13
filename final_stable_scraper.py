#!/usr/bin/env python3

from scraper import ShortMaxScraper
from selenium.webdriver.common.by import By
import logging
import time

def run_final_stable_scraper():
    """
    Final stable scraper with proven patterns and robust error handling
    Goal: Reach 800+ works by building on successful systematic approach
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    scraper = ShortMaxScraper()
    scraper.setup_driver()
    
    all_works = []
    
    try:
        print('=== FINAL STABLE SCRAPER ===')
        print('Building on proven patterns to reach 800+ works target...')
        
        print('\n--- Phase 1: Multiple Homepage Extractions ---')
        
        for attempt in range(6):  # Increase attempts to get more data
            try:
                print(f'Homepage extraction attempt {attempt + 1}/6')
                scraper.driver.get('https://shortmax.app/tabbar/home')
                time.sleep(8)
                
                if attempt == 0:
                    for i in range(30):
                        scraper.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1)
                elif attempt == 1:
                    for i in range(50):
                        scraper.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1.2)
                elif attempt == 2:
                    for i in range(80):
                        scraper.driver.execute_script(f"window.scrollTo(0, {i * 300});")
                        time.sleep(0.8)
                elif attempt == 3:
                    for i in range(40):
                        scraper.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)
                elif attempt == 4:
                    for i in range(100):
                        scraper.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1)
                        if i % 20 == 0:
                            time.sleep(3)
                else:
                    for i in range(150):
                        scraper.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(0.8)
                        if i % 25 == 0:
                            time.sleep(2)
                
                try:
                    attempt_works = scraper.extract_work_data_from_elements(f'Homepage Attempt {attempt + 1}')
                    all_works.extend(attempt_works)
                    print(f'Attempt {attempt + 1}: Extracted {len(attempt_works)} works')
                    print(f'Running total: {len(all_works)} works')
                except Exception as e:
                    print(f'Error in extraction for attempt {attempt + 1}: {e}')
                    continue
                    
            except Exception as e:
                print(f'Error in homepage attempt {attempt + 1}: {e}')
                continue
        
        if len(all_works) < 1000:  # Buffer for deduplication
            print('\n--- Phase 2: More Links Extraction ---')
            try:
                scraper.driver.get('https://shortmax.app/tabbar/home')
                time.sleep(5)
                
                for i in range(40):
                    scraper.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)
                
                more_links = scraper.driver.find_elements(By.XPATH, "//a[contains(@href, '/moreList/')]")
                more_hrefs = []
                
                for link in more_links:
                    try:
                        href = link.get_attribute('href')
                        if href and '/moreList/' in href:
                            more_hrefs.append(href)
                    except:
                        continue
                
                more_hrefs = list(set(more_hrefs))
                print(f'Found {len(more_hrefs)} unique More links')
                
                for i, href in enumerate(more_hrefs[:15]):  # Limit to avoid hanging
                    try:
                        print(f'Following More link {i+1}/{min(len(more_hrefs), 15)}: {href}')
                        scraper.driver.get(href)
                        time.sleep(6)
                        
                        for scroll in range(30):
                            scraper.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(1.5)
                        
                        section_name = f"More Link {i+1}"
                        try:
                            if 'title=' in href:
                                title_param = href.split('title=')[1].split('&')[0]
                                section_name = title_param.replace('%20', ' ')
                        except:
                            pass
                        
                        more_works = scraper.extract_work_data_from_elements(f'More: {section_name}')
                        all_works.extend(more_works)
                        print(f'Extracted {len(more_works)} works from {section_name}')
                        print(f'Running total: {len(all_works)} works')
                        
                        if len(all_works) > 1200:  # Buffer for deduplication
                            print('Reached sufficient works, proceeding to deduplication...')
                            break
                            
                    except Exception as e:
                        print(f'Error with More link {href}: {e}')
                        continue
                        
            except Exception as e:
                print(f'Error in More links phase: {e}')
        
        print('\n--- Phase 3: Improved Deduplication ---')
        print(f'Total works before deduplication: {len(all_works)}')
        
        if len(all_works) == 0:
            print('No works collected, cannot proceed with deduplication')
            return None
        
        scraper.all_works_data = all_works
        scraper.remove_duplicates()
        print(f'Unique works after improved deduplication: {len(scraper.all_works_data)}')
        
        if len(all_works) > 0:
            retention_rate = (len(scraper.all_works_data) / len(all_works)) * 100
            print(f'Deduplication retention rate: {retention_rate:.1f}%')
        
        print('\n--- Phase 4: Export and Analysis ---')
        csv_file = scraper.export_to_csv()
        print(f'Results exported to: {csv_file}')
        
        print('\n=== FINAL STABLE RESULTS ===')
        print(f'Total unique works found: {len(scraper.all_works_data)}')
        
        sorted_works = sorted(scraper.all_works_data, 
                            key=lambda x: scraper.parse_view_count_to_number(x['view_count']), 
                            reverse=True)
        
        print('\nTop 20 works by view count:')
        for i, work in enumerate(sorted_works[:20]):
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
        for sec, count in sorted(section_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f'{sec}: {count} works')
        
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
        
    finally:
        scraper.driver.quit()

if __name__ == "__main__":
    run_final_stable_scraper()
