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
        view_count_pattern = r'(\d+(?:\.\d+)?K)\b'
        match = re.search(view_count_pattern, text)
        if match:
            return match.group(1)
        
        simple_pattern = r'(\d+K)\b'
        match = re.search(simple_pattern, text)
        return match.group(1) if match else None
    
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
            
            for _ in range(3):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                
        except Exception as e:
            self.logger.warning(f"Error during scrolling: {e}")
    
    def extract_work_data_from_elements(self, section_name: str = "Unknown") -> List[Dict]:
        works_data = []
        
        try:
            work_containers = self.driver.find_elements(By.XPATH, 
                "//div[contains(@class, 'work') or contains(@class, 'item') or contains(@class, 'card') or contains(@class, 'drama')]")
            
            if not work_containers:
                work_containers = self.driver.find_elements(By.XPATH, 
                    "//div[.//img and .//text()[normalize-space()]]")
            
            processed_titles = set()
            
            for container in work_containers:
                try:
                    container_text = container.text.strip()
                    if not container_text or len(container_text) < 5:
                        continue
                    
                    lines = [line.strip() for line in container_text.split('\n') if line.strip()]
                    if not lines:
                        continue
                    
                    title = None
                    view_count = None
                    synopsis = ''
                    
                    for i, line in enumerate(lines):
                        if re.match(r'^\d+(?:\.\d+)?K?$', line):
                            view_count = line
                            continue
                        
                        view_match = re.search(r'(\d+(?:\.\d+)?K)\s*$', line)
                        if view_match:
                            view_count = view_match.group(1)
                            potential_title = line.replace(view_count, '').strip()
                            if potential_title and len(potential_title) > 3:
                                title = potential_title
                            continue
                        
                        if not title and len(line) > 3 and len(line) < 100:
                            if not line.startswith('[') and not line.lower() in ['new', 'hot', 'trending']:
                                title = line
                                continue
                        
                        if title and not synopsis and len(line) > 10 and len(line) < 300:
                            synopsis = line
                    
                    if title and title not in processed_titles:
                        processed_titles.add(title)
                        
                        if not view_count:
                            view_count = self.extract_view_count(container_text)
                        
                        work_data = {
                            'title': title,
                            'view_count': view_count or '',
                            'synopsis': synopsis,
                            'section': section_name,
                            'category': '',
                            'tags': ','.join(self.extract_tags(container_text)),
                            'episode_count': '',
                            'detailed_description': '',
                            'url': self.driver.current_url,
                            'scrape_timestamp': datetime.now().isoformat()
                        }
                        
                        works_data.append(work_data)
                        
                except Exception as e:
                    self.logger.debug(f"Error processing container: {e}")
                    continue
            
            if len(works_data) < 5:
                self.logger.info("Trying alternative extraction method")
                
                view_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'K') and string-length(text()) < 20]")
                
                for element in view_elements:
                    try:
                        text = element.text.strip()
                        if re.match(r'^\d+(?:\.\d+)?K$', text):
                            parent = element.find_element(By.XPATH, "./..")
                            parent_text = parent.text.strip()
                            
                            lines = [line.strip() for line in parent_text.split('\n') if line.strip()]
                            for line in lines:
                                if line != text and len(line) > 3 and len(line) < 100:
                                    if line not in processed_titles:
                                        processed_titles.add(line)
                                        
                                        work_data = {
                                            'title': line,
                                            'view_count': text,
                                            'synopsis': '',
                                            'section': section_name,
                                            'category': '',
                                            'tags': ','.join(self.extract_tags(parent_text)),
                                            'episode_count': '',
                                            'detailed_description': '',
                                            'url': self.driver.current_url,
                                            'scrape_timestamp': datetime.now().isoformat()
                                        }
                                        
                                        works_data.append(work_data)
                                        break
                    except Exception as e:
                        continue
            
            self.logger.info(f"Extracted {len(works_data)} works from {section_name}")
            return works_data
            
        except Exception as e:
            self.logger.error(f"Error extracting work data: {e}")
            return []
    
    def click_more_links(self):
        try:
            more_links = self.driver.find_elements(By.XPATH, "//a[contains(text(), 'More') or contains(text(), 'more')]")
            
            for link in more_links[:3]:
                try:
                    if link.is_displayed() and link.is_enabled():
                        self.driver.execute_script("arguments[0].click();", link)
                        time.sleep(3)
                        self.wait_for_page_load()
                        break
                except Exception as e:
                    continue
                    
        except Exception as e:
            self.logger.warning(f"Error clicking more links: {e}")
    
    def navigate_categories(self):
        all_category_data = []
        
        try:
            category_selectors = [
                "//button[contains(@class, 'tab') or contains(@class, 'category')]",
                "//div[contains(@class, 'tab') or contains(@class, 'category')]//button",
                "//a[contains(@class, 'tab') or contains(@class, 'category')]",
                "//*[contains(text(), 'Historical') or contains(text(), 'Urban') or contains(text(), 'Fantasy')]"
            ]
            
            category_elements = []
            for selector in category_selectors:
                elements = self.driver.find_elements(By.XPATH, selector)
                if elements:
                    category_elements = elements
                    self.logger.info(f"Found {len(elements)} category elements with selector: {selector}")
                    break
            
            if not category_elements:
                self.logger.warning("No category navigation elements found")
                return all_category_data
            
            for category_element in category_elements[:6]:  # Limit to avoid too many attempts
                try:
                    category_name = category_element.text.strip()
                    if category_name and len(category_name) > 2 and len(category_name) < 50:
                        self.logger.info(f"Attempting to scrape category: {category_name}")
                        
                        self.driver.execute_script("arguments[0].click();", category_element)
                        time.sleep(4)
                        self.wait_for_page_load()
                        self.scroll_and_load_content()
                        
                        category_works = self.extract_work_data_from_elements(f"Category: {category_name}")
                        for work in category_works:
                            work['category'] = category_name
                        
                        all_category_data.extend(category_works)
                        self.logger.info(f"Extracted {len(category_works)} works from category: {category_name}")
                        
                except Exception as e:
                    self.logger.warning(f"Error processing category element: {e}")
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
            self.driver.get(Config.BASE_URL)
            self.wait_for_page_load()
            
            self.scroll_and_load_content()
            
            homepage_works = self.extract_work_data_from_elements("Homepage")
            self.all_works_data.extend(homepage_works)
            
            self.click_more_links()
            
            more_works = self.extract_work_data_from_elements("Extended Homepage")
            self.all_works_data.extend(more_works)
            
            category_works = self.navigate_categories()
            self.all_works_data.extend(category_works)
            
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
        seen_titles = set()
        unique_works = []
        
        for work in self.all_works_data:
            title_key = work['title'].lower().strip()
            if title_key not in seen_titles and title_key:
                seen_titles.add(title_key)
                unique_works.append(work)
        
        self.all_works_data = unique_works
        self.logger.info(f"Removed duplicates, {len(self.all_works_data)} unique works remaining")
    
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
            self.logger.info("Starting ShortMax scraping process")
            
            self.scrape_all_sections()
            
            self.remove_duplicates()
            
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
