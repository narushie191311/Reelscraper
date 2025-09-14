#!/usr/bin/env python3

import time
import logging
import re
from datetime import datetime
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd

from config import Config

class TestScraper30:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.driver = None
        self.scraped_urls: Set[str] = set()
        self.all_works_data: List[Dict] = []
        self.max_items = 30  # 最初の30件のみ
        
    def setup_driver(self):
        try:
            chrome_options = Options()
            for option in Config.CHROME_OPTIONS:
                chrome_options.add_argument(option)
            
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            chrome_options.add_argument("--disable-images")
            chrome_options.add_argument("--remote-debugging-port=9222")
            
            chrome_binaries = [
                "/usr/bin/chromium-browser",
                "/snap/bin/chromium", 
                "/usr/bin/google-chrome",
                "/usr/bin/chromium"
            ]
            
            driver_created = False
            for binary_path in chrome_binaries:
                try:
                    chrome_options.binary_location = binary_path
                    self.logger.info(f"Trying Chrome binary: {binary_path}")
                    
                    try:
                        service = Service(ChromeDriverManager().install())
                        self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    except Exception as e:
                        self.logger.warning(f"ChromeDriverManager failed: {e}, trying without service")
                        self.driver = webdriver.Chrome(options=chrome_options)
                    
                    driver_created = True
                    self.logger.info(f"Chrome driver initialized successfully with {binary_path}")
                    break
                    
                except Exception as e:
                    self.logger.warning(f"Failed with {binary_path}: {e}")
                    continue
            
            if not driver_created:
                raise Exception("Could not initialize Chrome driver with any available binary")
                
        except Exception as e:
            self.logger.error(f"Failed to initialize Chrome driver: {e}")
            raise
    
    def wait_for_page_load(self, timeout: int = Config.WAIT_TIMEOUT):
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            time.sleep(2)
        except TimeoutException:
            self.logger.warning("Page load timeout, continuing anyway")
    
    def extract_view_count(self, text: str) -> Optional[str]:
        patterns = [
            r'(\d+(?:\.\d+)?K)\b',  # 1.5K, 123K
            r'(\d+K)\b',            # 123K
            r'(\d+(?:\.\d+)?M)\b',  # 1.5M, 2M
            r'(\d+M)\b',            # 2M
            r'(\d+(?:,\d{3})*)\s*(?:views?|Views?)',  # 1,234 views
            r'(\d+(?:\.\d+)?)\s*(?:thousand|k|K)',    # 1.5 thousand
            r'(\d+(?:\.\d+)?)\s*(?:million|m|M)',     # 1.5 million
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result = match.group(1)
                if 'thousand' in text.lower() or result.endswith(('k', 'K')):
                    if not result.endswith('K'):
                        result += 'K'
                elif 'million' in text.lower() or result.endswith(('m', 'M')):
                    if not result.endswith('M'):
                        result += 'M'
                return result
        
        return None
    
    def parse_view_count_to_number(self, view_count: str) -> int:
        if not view_count:
            return 0
        
        view_count = str(view_count).strip()
        
        if view_count.endswith('K'):
            return int(float(view_count[:-1]) * 1000)
        elif view_count.endswith('M'):
            return int(float(view_count[:-1]) * 1000000)
        else:
            try:
                return int(view_count.replace(',', ''))
            except ValueError:
                return 0
    
    def extract_work_data_from_elements(self, section_name: str = "Homepage") -> List[Dict]:
        """Extract work data from visible elements on current page"""
        works = []
        
        try:
            # Wait for content to load
            time.sleep(3)
            
            # Find all work cards/elements
            work_selectors = [
                "//div[contains(@class, 'work') or contains(@class, 'card') or contains(@class, 'item')]",
                "//a[contains(@href, '/work/') or contains(@href, '/drama/') or contains(@href, '/series/')]",
                "//div[contains(@class, 'drama') or contains(@class, 'series') or contains(@class, 'novel')]",
                "//*[contains(@class, 'title') or contains(@class, 'name')]//ancestor::*[contains(@class, 'card') or contains(@class, 'item')]"
            ]
            
            work_elements = []
            for selector in work_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        work_elements = elements
                        self.logger.info(f"Found {len(elements)} work elements using selector: {selector}")
                        break
                except Exception as e:
                    continue
            
            if not work_elements:
                self.logger.warning("No work elements found with any selector")
                return works
            
            for i, element in enumerate(work_elements):
                if len(works) >= self.max_items:  # 30件で停止
                    break
                    
                try:
                    work_data = self.extract_single_work_data(element, section_name)
                    if work_data and work_data.get('title'):
                        works.append(work_data)
                        self.logger.debug(f"Extracted work {len(works)}: {work_data['title']}")
                        
                except Exception as e:
                    self.logger.warning(f"Error extracting work data from element {i}: {e}")
                    continue
            
            self.logger.info(f"Extracted {len(works)} works from {section_name}")
            return works
            
        except Exception as e:
            self.logger.error(f"Error in extract_work_data_from_elements: {e}")
            return works
    
    def extract_single_work_data(self, element, section_name: str) -> Optional[Dict]:
        """Extract data from a single work element"""
        try:
            work_data = {
                'title': '',
                'view_count': '',
                'synopsis': '',
                'section': section_name,
                'category': '',
                'tags': '',
                'episode_count': '',
                'detailed_description': '',
                'url': '',
                'scrape_timestamp': datetime.now().isoformat()
            }
            
            # Try to find title
            title_selectors = [
                ".//h1", ".//h2", ".//h3", ".//h4", ".//h5", ".//h6",
                ".//*[contains(@class, 'title')]", 
                ".//*[contains(@class, 'name')]",
                ".//span[contains(@class, 'title')]",
                ".//div[contains(@class, 'title')]"
            ]
            
            for selector in title_selectors:
                try:
                    title_elem = element.find_element(By.XPATH, selector)
                    title_text = title_elem.text.strip()
                    if title_text and len(title_text) > 2:
                        work_data['title'] = title_text
                        break
                except:
                    continue
            
            # If no title found, try getting text from the element itself
            if not work_data['title']:
                try:
                    element_text = element.text.strip()
                    lines = element_text.split('\n')
                    for line in lines:
                        if line.strip() and len(line.strip()) > 2:
                            work_data['title'] = line.strip()
                            break
                except:
                    pass
            
            # Try to find view count
            try:
                element_text = element.text
                view_count = self.extract_view_count(element_text)
                if view_count:
                    work_data['view_count'] = view_count
            except:
                pass
            
            # Try to find URL
            try:
                if element.tag_name == 'a':
                    work_data['url'] = element.get_attribute('href')
                else:
                    link_elem = element.find_element(By.XPATH, ".//a")
                    work_data['url'] = link_elem.get_attribute('href')
            except:
                pass
            
            # Try to find synopsis/description
            try:
                element_text = element.text
                lines = element_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if len(line) > 20 and line != work_data['title']:
                        work_data['synopsis'] = line
                        break
            except:
                pass
            
            return work_data if work_data['title'] else None
            
        except Exception as e:
            self.logger.warning(f"Error extracting single work data: {e}")
            return None
    
    def remove_duplicates(self):
        """Remove duplicate works based on title"""
        seen_titles = set()
        unique_works = []
        
        for work in self.all_works_data:
            title = work.get('title', '').strip().lower()
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_works.append(work)
        
        self.all_works_data = unique_works
        self.logger.info(f"Removed duplicates: {len(self.all_works_data)} unique works remaining")
    
    def export_to_csv(self, filename: str = None) -> str:
        """Export collected data to CSV"""
        if not self.all_works_data:
            self.logger.warning("No data to export")
            return None
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"test_scraper_30_{timestamp}.csv"
        
        try:
            df = pd.DataFrame(self.all_works_data)
            df.to_csv(filename, index=False, encoding='utf-8')
            self.logger.info(f"Data exported to {filename}")
            return filename
        except Exception as e:
            self.logger.error(f"Error exporting to CSV: {e}")
            return None
    
    def run_test_scraper(self):
        """Run the test scraper to collect first 30 items"""
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        self.setup_driver()
        
        try:
            print('=== TEST SCRAPER - 最初の30件を取得 ===')
            
            # ホームページにアクセス
            print('ホームページにアクセス中...')
            self.driver.get('https://shortmax.app/tabbar/home')
            time.sleep(5)
            
            # 少しスクロールしてコンテンツを読み込み
            print('コンテンツを読み込み中...')
            for i in range(10):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            
            # ワークデータを抽出
            print('ワークデータを抽出中...')
            works = self.extract_work_data_from_elements('Homepage Test')
            self.all_works_data = works
            
            print(f'抽出完了: {len(self.all_works_data)}件のワークを取得')
            
            # CSVで出力
            csv_file = self.export_to_csv()
            if csv_file:
                print(f'CSVファイルに出力完了: {csv_file}')
                
                # 結果の概要を表示
                print('\n=== 取得したデータの概要 ===')
                for i, work in enumerate(self.all_works_data[:10], 1):
                    print(f'{i}. {work["title"]} - {work["view_count"]} views')
                
                if len(self.all_works_data) > 10:
                    print(f'... 他 {len(self.all_works_data) - 10}件')
                
                return csv_file
            else:
                print('CSVファイルの出力に失敗しました')
                return None
                
        except Exception as e:
            print(f'エラーが発生しました: {e}')
            return None
        finally:
            if self.driver:
                self.driver.quit()

if __name__ == "__main__":
    scraper = TestScraper30()
    result = scraper.run_test_scraper()
    if result:
        print(f'\n✅ テスト完了: {result}')
    else:
        print('\n❌ テスト失敗')