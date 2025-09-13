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

class ShortMaxScraper:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.driver = None
        self.scraped_urls: Set[str] = set()
        self.all_works_data: List[Dict] = []
        
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
                elif ',' in result:
                    num = int(result.replace(',', ''))
                    if num >= 1000:
                        result = f"{num/1000:.1f}K"
                    else:
                        result = f"{num}"
                return result
        
        return None
    
    def extract_tags(self, text: str) -> List[str]:
        tags = []
        if "[Dubbed]" in text:
            tags.append("Dubbed")
        if "flash married" in text.lower():
            tags.append("flash married")
        if "NEW" in text:
            tags.append("NEW")
        return tags
    
    def scroll_and_load_content(self):
        try:
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            scroll_attempts = 0
            max_scrolls = 15  # Increased from 3 to 15 to load more content
            
            while scroll_attempts < max_scrolls:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(4)  # Increased wait time to ensure content loads
                
                if scroll_attempts % 3 == 0:
                    scroll_position = (scroll_attempts + 1) * 1000
                    self.driver.execute_script(f"window.scrollTo(0, {scroll_position});")
                    time.sleep(2)
                
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight + 1000);")
                    time.sleep(3)
                    final_height = self.driver.execute_script("return document.body.scrollHeight")
                    if final_height == new_height:
                        break
                    else:
                        new_height = final_height
                    
                last_height = new_height
                scroll_attempts += 1
                
            self.logger.info(f"Completed scrolling after {scroll_attempts} attempts, final height: {last_height}")
                
        except Exception as e:
            self.logger.warning(f"Error during scrolling: {e}")
    
    def extract_work_data_from_elements(self, section_name: str) -> List[Dict[str, str]]:
        works = []
        
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            text_works = self.parse_page_text_for_works(page_text, section_name)
            works.extend(text_works)
            self.logger.info(f"Extracted {len(text_works)} works from page text parsing")
            
            work_selectors = [
                "//*[string-length(text()) > 5 and string-length(text()) < 150]",
                "//img[contains(@src, 'cover') or contains(@src, 'images') or contains(@src, 'static')]/..",
                "//*[contains(text(), 'K') or contains(text(), 'M')]",
                "//*[contains(text(), 'Alpha') or contains(text(), 'CEO') or contains(text(), 'Billionaire') or contains(text(), 'Princess') or contains(text(), 'Marriage') or contains(text(), 'Love') or contains(text(), 'Revenge')]",
                "//*[contains(text(), '[Dubbed]') or contains(text(), 'Dubbed') or contains(text(), 'flash married') or contains(text(), 'NEW')]",
                "//*[contains(text(), 'Premium') or contains(text(), 'Popular') or contains(text(), 'Trending') or contains(text(), 'Original')]"
            ]
            
            all_elements = []
            for selector in work_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    all_elements.extend(elements)
                except:
                    continue
            
            seen = set()
            unique_elements = []
            for elem in all_elements:
                try:
                    elem_id = id(elem)
                    if elem_id not in seen:
                        seen.add(elem_id)
                        unique_elements.append(elem)
                except:
                    continue
            
            self.logger.info(f"Found {len(unique_elements)} potential work elements in {section_name}")
            
            for element in unique_elements:
                try:
                    element_text = element.text.strip()
                    if not element_text or len(element_text) < 3:
                        continue
                    
                    skip_keywords = ['Install', 'Download', 'Sign in', 'Get Bonus', 'Classification', 'Search for more', 'Every moment', 'minutes ago', 'seconds ago']
                    if any(keyword in element_text for keyword in skip_keywords):
                        continue
                    
                    work_data = self.parse_work_element(element, element_text, section_name)
                    if work_data and (work_data.get('title') or work_data.get('view_count')):
                        works.append(work_data)
                        
                except Exception as e:
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error extracting work data from {section_name}: {e}")
        
        self.logger.info(f"Successfully extracted {len(works)} works from {section_name}")
        return works
    
    def handle_pagination(self, section_name: str) -> List[Dict[str, str]]:
        pagination_works = []
        
        try:
            load_more_selectors = [
                "//button[contains(text(), 'Load More') or contains(text(), 'More') or contains(text(), 'Next')]",
                "//a[contains(text(), 'Load More') or contains(text(), 'More') or contains(text(), 'Next')]",
                "//div[contains(@class, 'load-more') or contains(@class, 'pagination')]//button",
                "//div[contains(@class, 'load-more') or contains(@class, 'pagination')]//a"
            ]
            
            page_count = 0
            max_pages = 10  # Limit to avoid infinite loops
            
            while page_count < max_pages:
                load_more_found = False
                
                for selector in load_more_selectors:
                    try:
                        load_more_elements = self.driver.find_elements(By.XPATH, selector)
                        if load_more_elements:
                            for element in load_more_elements:
                                if element.is_displayed() and element.is_enabled():
                                    self.logger.info(f"Found pagination element in {section_name}, clicking...")
                                    self.driver.execute_script("arguments[0].click();", element)
                                    time.sleep(3)
                                    self.wait_for_page_load()
                                    self.scroll_and_load_content()
                                    
                                    new_works = self.extract_work_data_from_elements(section_name)
                                    pagination_works.extend(new_works)
                                    self.logger.info(f"Extracted {len(new_works)} additional works from pagination")
                                    
                                    load_more_found = True
                                    page_count += 1
                                    break
                    except Exception as e:
                        continue
                
                if not load_more_found:
                    break
                    
        except Exception as e:
            self.logger.warning(f"Error handling pagination for {section_name}: {e}")
        
        return pagination_works
    
    def parse_page_text_for_works(self, page_text: str, section_name: str) -> List[Dict[str, str]]:
        works = []
        
        try:
            lines = page_text.split('\n')
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line or len(line) < 3:
                    continue
                
                skip_patterns = ['Install', 'Download', 'Sign in', 'Get Bonus', 'Search for', 'Every moment', 'minutes ago', 'seconds ago', 'Home', 'Shorts', 'My List', 'Profile']
                if any(pattern in line for pattern in skip_patterns):
                    continue
                
                view_count = self.extract_view_count(line)
                if view_count:
                    title = None
                    tags = []
                    
                    search_range = range(max(0, i-5), min(len(lines), i+6))
                    for j in search_range:
                        nearby_line = lines[j].strip()
                        if not nearby_line or j == i:
                            continue
                        
                        if self.extract_view_count(nearby_line):
                            continue
                        
                        if (len(nearby_line) > 8 and len(nearby_line) < 120 and 
                            not any(skip in nearby_line for skip in skip_patterns)):
                            
                            if not title or len(nearby_line) > len(title):
                                title = nearby_line
                        
                        line_tags = self.extract_tags(nearby_line)
                        tags.extend(line_tags)
                    
                    if title and len(title) > 5:
                        work_data = {
                            'title': title,
                            'view_count': view_count,
                            'synopsis': '',
                            'section': section_name,
                            'category': '',
                            'tags': ', '.join(set(tags)) if tags else '',
                            'episode_count': '',
                            'detailed_description': '',
                            'url': self.driver.current_url,
                            'scrape_timestamp': datetime.now().isoformat()
                        }
                        works.append(work_data)
                
                elif (len(line) > 10 and len(line) < 120 and 
                      any(keyword in line.lower() for keyword in ['alpha', 'ceo', 'billionaire', 'princess', 'marriage', 'love', 'revenge', 'wife', 'husband', 'drama']) and
                      not any(skip in line for skip in skip_patterns)):
                    
                    view_count = None
                    tags = []
                    
                    search_range = range(max(0, i-3), min(len(lines), i+4))
                    for j in search_range:
                        if j == i:
                            continue
                        nearby_line = lines[j].strip()
                        if not nearby_line:
                            continue
                        
                        nearby_view_count = self.extract_view_count(nearby_line)
                        if nearby_view_count:
                            view_count = nearby_view_count
                        
                        line_tags = self.extract_tags(nearby_line)
                        tags.extend(line_tags)
                    
                    if view_count or any(keyword in line.lower() for keyword in ['dubbed', 'flash married', 'alpha', 'billionaire']):
                        work_data = {
                            'title': line,
                            'view_count': view_count or '0K',
                            'synopsis': '',
                            'section': section_name,
                            'category': '',
                            'tags': ', '.join(set(tags)) if tags else '',
                            'episode_count': '',
                            'detailed_description': '',
                            'url': self.driver.current_url,
                            'scrape_timestamp': datetime.now().isoformat()
                        }
                        works.append(work_data)
                    
        except Exception as e:
            self.logger.warning(f"Error parsing page text: {e}")
        
        return works
    
    def parse_work_element(self, element, element_text: str, section_name: str) -> Dict[str, str]:
        try:
            lines = element_text.split('\n')
            title = ""
            view_count = ""
            tags = []
            synopsis = ""
            
            skip_keywords = ['Install', 'Download', 'Sign in', 'Get Bonus', 'Classification', 'Search for more', 'Every moment', 'minutes ago', 'seconds ago']
            if any(keyword in element_text for keyword in skip_keywords):
                return None
            
            for line in lines:
                line = line.strip()
                if not line or len(line) < 3:
                    continue
                
                extracted_view_count = self.extract_view_count(line)
                if extracted_view_count and not extracted_view_count.startswith('0'):
                    view_count = extracted_view_count
                
                line_tags = self.extract_tags(line)
                if line_tags:
                    tags.extend(line_tags)
                
                if (len(line) > 5 and len(line) < 150 and 
                    not self.extract_view_count(line) and
                    not any(skip in line for skip in ['More', 'Play', 'Episode', 'minutes', 'seconds', 'ago'])):
                    
                    if not title or len(line) > len(title):
                        title = line
                
                elif len(line) > 20 and len(line) < 300:
                    if not synopsis and not self.extract_view_count(line):
                        synopsis = line
            
            if title or view_count or tags:
                if not title or len(title) < 8:
                    try:
                        parent = element.find_element(By.XPATH, "..")
                        parent_text = parent.text.strip()
                        parent_lines = parent_text.split('\n')
                        for parent_line in parent_lines:
                            parent_line = parent_line.strip()
                            if (len(parent_line) > 8 and len(parent_line) < 120 and 
                                not self.extract_view_count(parent_line) and
                                not any(skip in parent_line for skip in skip_keywords)):
                                if not title or len(parent_line) > len(title):
                                    title = parent_line
                    except:
                        pass
                
                if not title:
                    if tags and view_count:
                        title = f"Work with {', '.join(tags)}"
                    elif view_count:
                        title = f"Work ({view_count} views)"
                    else:
                        title = "Unknown Work"
                
                if not view_count:
                    view_count = "0K"
                
                return {
                    'title': title,
                    'view_count': view_count,
                    'synopsis': synopsis,
                    'section': section_name,
                    'category': '',
                    'tags': ', '.join(set(tags)) if tags else '',
                    'episode_count': '',
                    'detailed_description': '',
                    'url': self.driver.current_url,
                    'scrape_timestamp': datetime.now().isoformat()
                }
        except Exception as e:
            pass
        
        return None
    
    def click_more_links(self):
        self.logger.info("Skipping 'More' links - they require user authentication")
        return []
    
    def navigate_categories(self):
        all_category_data = []
        
        try:
            self.driver.get(Config.BASE_URL)
            time.sleep(3)
            self.wait_for_page_load()
            
            category_selectors = [
                "//div[contains(@class, 'tab')]",
                "//button[contains(@class, 'tab')]", 
                "//*[@role='tab']",
                "//div[contains(text(), 'Historical') or contains(text(), 'Urban') or contains(text(), 'High Fantasy') or contains(text(), 'Elite Families') or contains(text(), 'Werewolf') or contains(text(), 'Modern Love')]",
                "//a[contains(text(), 'Historical') or contains(text(), 'Urban') or contains(text(), 'Fantasy')]"
            ]
            
            category_elements = []
            for selector in category_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        category_elements = elements
                        self.logger.info(f"Found {len(elements)} category elements with selector: {selector}")
                        break
                except:
                    continue
            
            if not category_elements:
                self.logger.warning("No category navigation elements found")
                return all_category_data
            
            self.logger.info(f"Found {len(category_elements)} category elements")
            
            categories = []
            for element in category_elements:
                try:
                    category_name = element.text.strip()
                    if category_name and len(category_name) > 2 and len(category_name) < 50:
                        categories.append(category_name)
                except:
                    continue
            
            self.logger.info(f"Will scrape categories: {categories}")
            
            for category_name in categories:
                try:
                    self.logger.info(f"Scraping category: {category_name}")
                    
                    category_element = None
                    for selector in [
                        f"//*[text()='{category_name}']",
                        f"//*[contains(text(), '{category_name}')]",
                        f"//div[text()='{category_name}']",
                        f"//button[text()='{category_name}']"
                    ]:
                        try:
                            category_element = self.driver.find_element(By.XPATH, selector)
                            break
                        except:
                            continue
                    
                    if not category_element:
                        self.logger.warning(f"Could not find clickable element for category: {category_name}")
                        continue
                    self.driver.execute_script("arguments[0].click();", category_element)
                    time.sleep(4)
                    self.wait_for_page_load()
                    
                    self.scroll_and_load_content()
                    
                    category_works = self.extract_work_data_from_elements(f"Category: {category_name}")
                    for work in category_works:
                        work['category'] = category_name
                    
                    all_category_data.extend(category_works)
                    self.logger.info(f"Extracted {len(category_works)} works from category: {category_name}")
                    
                    pagination_works = self.handle_pagination(f"Category: {category_name}")
                    for work in pagination_works:
                        work['category'] = category_name
                    all_category_data.extend(pagination_works)
                    
                except Exception as e:
                    self.logger.warning(f"Error processing category {category_name}: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error navigating categories: {e}")
        
        return all_category_data
    
    def scrape_individual_work_details(self, work_url: str) -> Dict:
        additional_data = {
            'episode_count': '',
            'detailed_description': ''
        }
        
        if work_url in self.scraped_urls:
            return additional_data
            
        try:
            original_url = self.driver.current_url
            self.driver.get(work_url)
            self.wait_for_page_load()
            
            try:
                episode_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Episode') or contains(text(), 'episode')]")
                for element in episode_elements:
                    text = element.text
                    episode_match = re.search(r'(\d+)\s*(?:Episode|episode)', text)
                    if episode_match:
                        additional_data['episode_count'] = episode_match.group(1)
                        break
            except:
                pass
            
            try:
                description_elements = self.driver.find_elements(By.XPATH, "//p[string-length(text()) > 50] | //div[string-length(text()) > 50]")
                for element in description_elements[:3]:
                    text = element.text.strip()
                    if len(text) > 50 and len(text) < 500:
                        additional_data['detailed_description'] = text
                        break
            except:
                pass
            
            self.scraped_urls.add(work_url)
            self.driver.get(original_url)
            self.wait_for_page_load()
            
        except Exception as e:
            self.logger.warning(f"Error scraping individual work details from {work_url}: {e}")
        
        return additional_data
    
    def scrape_all_sections(self):
        try:
            all_works = []
            
            self.logger.info("=== PHASE 1: Scraping homepage sections ===")
            self.driver.get(Config.BASE_URL)
            self.wait_for_page_load()
            time.sleep(5)
            self.scroll_and_load_content()
            homepage_works = self.extract_work_data_from_elements("Homepage")
            all_works.extend(homepage_works)
            self.logger.info(f"Phase 1 complete: {len(homepage_works)} works from homepage")
            
            self.logger.info("=== PHASE 2: Following 'More' links ===")
            self.driver.get(Config.BASE_URL)
            time.sleep(3)
            self.wait_for_page_load()
            more_works = self.click_more_links()
            all_works.extend(more_works)
            self.logger.info(f"Phase 2 complete: {len(more_works)} additional works from More links")
            
            self.logger.info("=== PHASE 3: Comprehensive category navigation ===")
            category_works = self.navigate_categories()
            all_works.extend(category_works)
            self.logger.info(f"Phase 3 complete: {len(category_works)} works from categories")
            
            self.all_works_data = all_works
            self.logger.info(f"Total works collected: {len(self.all_works_data)}")
            
        except Exception as e:
            self.logger.error(f"Error in scrape_all_sections: {e}")
    
    def enhance_with_individual_details(self):
        unique_urls = set()
        for work in self.all_works_data:
            if work['url'] not in unique_urls:
                unique_urls.add(work['url'])
        
        self.logger.info(f"Enhancing {len(unique_urls)} unique works with individual details")
        
        for i, work in enumerate(self.all_works_data):
            if i % 10 == 0:
                self.logger.info(f"Enhanced {i}/{len(self.all_works_data)} works")
            
            try:
                if work['title'] and len(work['title']) > 3:
                    individual_url = f"https://shortmax.app/search?q={work['title'].replace(' ', '+')}"
                    additional_data = self.scrape_individual_work_details(individual_url)
                    work.update(additional_data)
            except Exception as e:
                continue
    
    def remove_duplicates(self):
        seen_combinations = set()
        unique_works = []
        
        for work in self.all_works_data:
            title = work['title'].strip()
            title_key = title.lower()
            view_count = work.get('view_count', '0K')
            section = work.get('section', '')
            
            skip_keywords = [
                'install', 'download', 'sign in', 'get bonus', 'classification',
                'home', 'shorts', 'my list', 'profile', 'search for more',
                'every moment', 'user agreement', 'privacy policy'
            ]
            
            if (not title or 
                len(title) < 2 or
                title_key in skip_keywords or
                any(title_key == keyword for keyword in skip_keywords)):
                continue
            
            dedup_key = f"{title_key}|{view_count}|{section}"
            
            if dedup_key not in seen_combinations:
                seen_combinations.add(dedup_key)
                unique_works.append(work)
            else:
                category = work.get('category', '')
                if category:
                    existing_categories = [w.get('category', '') for w in unique_works 
                                         if w['title'].lower().strip() == title_key]
                    if category not in existing_categories:
                        unique_works.append(work)
        
        self.all_works_data = unique_works
        self.logger.info(f"Removed duplicates, {len(self.all_works_data)} unique works remaining")
    
    def parse_view_count_to_number(self, view_count_str):
        """Convert view count string like '1498.17K' to number for comparison"""
        try:
            if not view_count_str or view_count_str == 'N/A':
                return 0
            
            view_count_str = view_count_str.strip().upper()
            if 'K' in view_count_str:
                return float(view_count_str.replace('K', '')) * 1000
            elif 'M' in view_count_str:
                return float(view_count_str.replace('M', '')) * 1000000
            else:
                return float(view_count_str)
        except:
            return 0
    
    def export_to_csv(self, filename: str = "shortmax_works_data.csv"):
        try:
            if not self.all_works_data:
                self.logger.warning("No data to export")
                return
            
            df = pd.DataFrame(self.all_works_data)
            
            for col in Config.CSV_COLUMNS:
                if col not in df.columns:
                    df[col] = ''
            
            df = df[Config.CSV_COLUMNS]
            
            df.to_csv(filename, index=False, encoding='utf-8')
            self.logger.info(f"Data exported to {filename}")
            self.logger.info(f"Total works exported: {len(df)}")
            
            return filename
            
        except Exception as e:
            self.logger.error(f"Error exporting to CSV: {e}")
            return None
    
    def run_scraper(self):
        try:
            self.setup_driver()
            self.logger.info("Starting comprehensive ShortMax scraping process")
            
            self.scrape_all_sections()
            
            self.logger.info("=== PHASE 4: Removing duplicates ===")
            self.remove_duplicates()
            self.logger.info(f"Total unique works found: {len(self.all_works_data)}")
            
            self.logger.info("=== PHASE 5: Enhancing with individual details ===")
            self.enhance_with_individual_details()
            
            csv_file = self.export_to_csv()
            
            self.logger.info("Scraping completed successfully")
            return csv_file
            
        except Exception as e:
            self.logger.error(f"Error in run_scraper: {e}")
            return None
            
        finally:
            if self.driver:
                self.driver.quit()
                self.logger.info("Driver closed")
