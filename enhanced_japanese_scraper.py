#!/usr/bin/env python3

import time
import logging
import re
import asyncio
import aiohttp
import concurrent.futures
import threading
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
from queue import Queue
import json

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

class EnhancedJapaneseScraper:
    def __init__(self, max_workers: int = 4):
        self.logger = logging.getLogger(__name__)
        self.driver = None
        self.scraped_urls: Set[str] = set()
        self.all_works_data: List[Dict] = []
        self.max_workers = max_workers
        self.session = None
        self.lock = threading.Lock()
        
    def setup_driver(self):
        try:
            chrome_options = Options()
            for option in Config.CHROME_OPTIONS:
                chrome_options.add_argument(option)
            
            # 日本語対応の設定を追加
            chrome_options.add_argument("--lang=ja")
            chrome_options.add_argument("--accept-lang=ja,en-US,en")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            chrome_options.add_argument("--disable-images")
            chrome_options.add_argument("--remote-debugging-port=9222")
            
            # 日本語フォントの設定
            prefs = {
                "intl.accept_languages": "ja,en-US,en",
                "profile.default_content_setting_values": {
                    "cookies": 2,
                    "images": 2,
                    "javascript": 1,
                    "plugins": 2,
                    "popups": 2,
                    "geolocation": 2,
                    "notifications": 2,
                    "media_stream": 2,
                }
            }
            chrome_options.add_experimental_option("prefs", prefs)
            
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
    
    async def setup_session(self):
        """非同期HTTPセッションを設定"""
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept-Language': 'ja,en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            }
        )
    
    async def close_session(self):
        """非同期HTTPセッションを閉じる"""
        if self.session:
            await self.session.close()
    
    def wait_for_page_load(self, timeout: int = Config.WAIT_TIMEOUT):
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            time.sleep(2)
        except TimeoutException:
            self.logger.warning("Page load timeout, continuing anyway")
    
    def extract_view_count(self, text: str) -> Optional[str]:
        """再生数を抽出（日本語対応）"""
        patterns = [
            r'(\d+(?:\.\d+)?K)\b',  # 1.5K, 123K
            r'(\d+K)\b',            # 123K
            r'(\d+(?:\.\d+)?M)\b',  # 1.5M, 2M
            r'(\d+M)\b',            # 2M
            r'(\d+(?:,\d{3})*)\s*(?:views?|Views?|再生|回)',  # 1,234 views, 1234再生
            r'(\d+(?:\.\d+)?)\s*(?:thousand|k|K|千)',    # 1.5 thousand, 1.5千
            r'(\d+(?:\.\d+)?)\s*(?:million|m|M|万)',     # 1.5 million, 1.5万
            r'(\d+(?:\.\d+)?万)',  # 日本語の万
            r'(\d+(?:\.\d+)?千)',  # 日本語の千
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result = match.group(1)
                if 'thousand' in text.lower() or result.endswith(('k', 'K', '千')):
                    if not result.endswith('K'):
                        if result.endswith('千'):
                            result = result.replace('千', 'K')
                        else:
                            result += 'K'
                elif 'million' in text.lower() or result.endswith(('m', 'M', '万')):
                    if not result.endswith('M'):
                        if result.endswith('万'):
                            result = result.replace('万', 'M')
                        else:
                            result += 'M'
                elif ',' in result:
                    num = int(result.replace(',', ''))
                    if num >= 1000:
                        result = f"{num/1000:.1f}K"
                    else:
                        result = f"{num}"
                return result
        
        return None
    
    def extract_favorite_count(self, text: str) -> Optional[str]:
        """お気に入り数を抽出（日本語対応）"""
        patterns = [
            r'(\d+(?:\.\d+)?K)\s*(?:favorites?|likes?|お気に入り|いいね)',  # 1.5K favorites
            r'(\d+K)\s*(?:favorites?|likes?|お気に入り|いいね)',            # 123K favorites
            r'(\d+(?:\.\d+)?M)\s*(?:favorites?|likes?|お気に入り|いいね)',  # 1.5M favorites
            r'(\d+M)\s*(?:favorites?|likes?|お気に入り|いいね)',            # 2M favorites
            r'(\d+(?:,\d{3})*)\s*(?:favorites?|likes?|お気に入り|いいね)',  # 1,234 favorites
            r'(\d+(?:\.\d+)?)\s*(?:thousand|k|K|千)\s*(?:favorites?|likes?|お気に入り|いいね)',
            r'(\d+(?:\.\d+)?)\s*(?:million|m|M|万)\s*(?:favorites?|likes?|お気に入り|いいね)',
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
    
    def extract_tags(self, text: str) -> List[str]:
        """タグを抽出（日本語対応）"""
        tags = []
        tag_patterns = [
            (r'\[Dubbed\]', "Dubbed"),
            (r'\[吹き替え\]', "Dubbed"),
            (r'flash married', "flash married"),
            (r'NEW', "NEW"),
            (r'新着', "NEW"),
            (r'Premium', "Premium"),
            (r'プレミアム', "Premium"),
            (r'Popular', "Popular"),
            (r'人気', "Popular"),
            (r'Trending', "Trending"),
            (r'トレンド', "Trending"),
            (r'Original', "Original"),
            (r'オリジナル', "Original"),
        ]
        
        for pattern, tag in tag_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                tags.append(tag)
        
        return tags
    
    def scroll_and_load_content(self):
        """コンテンツを読み込むためにスクロール"""
        try:
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            scroll_attempts = 0
            max_scrolls = 20  # より多くのコンテンツを読み込む
            
            while scroll_attempts < max_scrolls:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
                
                if scroll_attempts % 5 == 0:
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
        """作品データを要素から抽出（日本語対応強化）"""
        works = []
        
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            text_works = self.parse_page_text_for_works(page_text, section_name)
            works.extend(text_works)
            self.logger.info(f"Extracted {len(text_works)} works from page text parsing")
            
            # より包括的なセレクター
            work_selectors = [
                "//*[string-length(text()) > 5 and string-length(text()) < 200]",
                "//img[contains(@src, 'cover') or contains(@src, 'images') or contains(@src, 'static')]/..",
                "//*[contains(text(), 'K') or contains(text(), 'M') or contains(text(), '万') or contains(text(), '千')]",
                "//*[contains(text(), 'Alpha') or contains(text(), 'CEO') or contains(text(), 'Billionaire') or contains(text(), 'Princess') or contains(text(), 'Marriage') or contains(text(), 'Love') or contains(text(), 'Revenge')]",
                "//*[contains(text(), '[Dubbed]') or contains(text(), 'Dubbed') or contains(text(), 'flash married') or contains(text(), 'NEW') or contains(text(), '吹き替え') or contains(text(), '新着')]",
                "//*[contains(text(), 'Premium') or contains(text(), 'Popular') or contains(text(), 'Trending') or contains(text(), 'Original') or contains(text(), 'プレミアム') or contains(text(), '人気') or contains(text(), 'トレンド') or contains(text(), 'オリジナル')]",
                "//*[contains(text(), 'お気に入り') or contains(text(), 'いいね') or contains(text(), 'favorites') or contains(text(), 'likes')]",
                "//*[contains(text(), '再生') or contains(text(), 'views')]"
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
                    
                    skip_keywords = ['Install', 'Download', 'Sign in', 'Get Bonus', 'Classification', 'Search for more', 'Every moment', 'minutes ago', 'seconds ago', 'インストール', 'ダウンロード', 'サインイン', 'ボーナス', '分類', '検索', '毎瞬間', '分前', '秒前']
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
    
    def parse_page_text_for_works(self, page_text: str, section_name: str) -> List[Dict[str, str]]:
        """ページテキストから作品を解析（日本語対応強化）"""
        works = []
        
        try:
            lines = page_text.split('\n')
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line or len(line) < 3:
                    continue
                
                skip_patterns = ['Install', 'Download', 'Sign in', 'Get Bonus', 'Search for', 'Every moment', 'minutes ago', 'seconds ago', 'Home', 'Shorts', 'My List', 'Profile', 'インストール', 'ダウンロード', 'サインイン', 'ボーナス', '検索', '毎瞬間', '分前', '秒前', 'ホーム', 'ショート', 'マイリスト', 'プロフィール']
                if any(pattern in line for pattern in skip_patterns):
                    continue
                
                view_count = self.extract_view_count(line)
                favorite_count = self.extract_favorite_count(line)
                
                if view_count or favorite_count:
                    title = None
                    synopsis = ""
                    tags = []
                    
                    search_range = range(max(0, i-5), min(len(lines), i+6))
                    for j in search_range:
                        nearby_line = lines[j].strip()
                        if not nearby_line or j == i:
                            continue
                        
                        if self.extract_view_count(nearby_line) or self.extract_favorite_count(nearby_line):
                            continue
                        
                        if (len(nearby_line) > 8 and len(nearby_line) < 150 and 
                            not any(skip in nearby_line for skip in skip_patterns)):
                            
                            if not title or len(nearby_line) > len(title):
                                title = nearby_line
                        
                        if len(nearby_line) > 20 and len(nearby_line) < 300:
                            if not synopsis and not self.extract_view_count(nearby_line) and not self.extract_favorite_count(nearby_line):
                                synopsis = nearby_line
                        
                        line_tags = self.extract_tags(nearby_line)
                        tags.extend(line_tags)
                    
                    if title and len(title) > 5:
                        work_data = {
                            'title': title,
                            'view_count': view_count or '0K',
                            'favorite_count': favorite_count or '0K',
                            'synopsis': synopsis,
                            'section': section_name,
                            'category': '',
                            'tags': ', '.join(set(tags)) if tags else '',
                            'episode_count': '',
                            'detailed_description': '',
                            'url': self.driver.current_url,
                            'scrape_timestamp': datetime.now().isoformat()
                        }
                        works.append(work_data)
                
                elif (len(line) > 10 and len(line) < 150 and 
                      any(keyword in line.lower() for keyword in ['alpha', 'ceo', 'billionaire', 'princess', 'marriage', 'love', 'revenge', 'wife', 'husband', 'drama', 'アルファ', 'CEO', '億万長者', '王女', '結婚', '愛', '復讐', '妻', '夫', 'ドラマ']) and
                      not any(skip in line for skip in skip_patterns)):
                    
                    view_count = None
                    favorite_count = None
                    tags = []
                    synopsis = ""
                    
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
                        
                        nearby_favorite_count = self.extract_favorite_count(nearby_line)
                        if nearby_favorite_count:
                            favorite_count = nearby_favorite_count
                        
                        line_tags = self.extract_tags(nearby_line)
                        tags.extend(line_tags)
                        
                        if len(nearby_line) > 20 and len(nearby_line) < 300:
                            if not synopsis and not self.extract_view_count(nearby_line) and not self.extract_favorite_count(nearby_line):
                                synopsis = nearby_line
                    
                    if view_count or favorite_count or any(keyword in line.lower() for keyword in ['dubbed', 'flash married', 'alpha', 'billionaire', '吹き替え', 'アルファ', '億万長者']):
                        work_data = {
                            'title': line,
                            'view_count': view_count or '0K',
                            'favorite_count': favorite_count or '0K',
                            'synopsis': synopsis,
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
        """作品要素を解析（日本語対応強化）"""
        try:
            lines = element_text.split('\n')
            title = ""
            view_count = ""
            favorite_count = ""
            tags = []
            synopsis = ""
            
            skip_keywords = ['Install', 'Download', 'Sign in', 'Get Bonus', 'Classification', 'Search for more', 'Every moment', 'minutes ago', 'seconds ago', 'インストール', 'ダウンロード', 'サインイン', 'ボーナス', '分類', '検索', '毎瞬間', '分前', '秒前']
            if any(keyword in element_text for keyword in skip_keywords):
                return None
            
            for line in lines:
                line = line.strip()
                if not line or len(line) < 3:
                    continue
                
                extracted_view_count = self.extract_view_count(line)
                if extracted_view_count and not extracted_view_count.startswith('0'):
                    view_count = extracted_view_count
                
                extracted_favorite_count = self.extract_favorite_count(line)
                if extracted_favorite_count and not extracted_favorite_count.startswith('0'):
                    favorite_count = extracted_favorite_count
                
                line_tags = self.extract_tags(line)
                if line_tags:
                    tags.extend(line_tags)
                
                if (len(line) > 5 and len(line) < 200 and 
                    not self.extract_view_count(line) and
                    not self.extract_favorite_count(line) and
                    not any(skip in line for skip in ['More', 'Play', 'Episode', 'minutes', 'seconds', 'ago', 'もっと', '再生', 'エピソード', '分', '秒', '前'])):
                    
                    if not title or len(line) > len(title):
                        title = line
                
                elif len(line) > 20 and len(line) < 400:
                    if not synopsis and not self.extract_view_count(line) and not self.extract_favorite_count(line):
                        synopsis = line
            
            if title or view_count or favorite_count or tags:
                if not title or len(title) < 8:
                    try:
                        parent = element.find_element(By.XPATH, "..")
                        parent_text = parent.text.strip()
                        parent_lines = parent_text.split('\n')
                        for parent_line in parent_lines:
                            parent_line = parent_line.strip()
                            if (len(parent_line) > 8 and len(parent_line) < 150 and 
                                not self.extract_view_count(parent_line) and
                                not self.extract_favorite_count(parent_line) and
                                not any(skip in parent_line for skip in skip_keywords)):
                                if not title or len(parent_line) > len(title):
                                    title = parent_line
                    except:
                        pass
                
                if not title:
                    if tags and (view_count or favorite_count):
                        title = f"Work with {', '.join(tags)}"
                    elif view_count or favorite_count:
                        title = f"Work ({view_count} views, {favorite_count} favorites)"
                    else:
                        title = "Unknown Work"
                
                if not view_count:
                    view_count = "0K"
                
                if not favorite_count:
                    favorite_count = "0K"
                
                return {
                    'title': title,
                    'view_count': view_count,
                    'favorite_count': favorite_count,
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
    
    def get_japanese_urls(self) -> List[str]:
        """日本語ページのURLを取得"""
        japanese_urls = [
            'https://shortmax.app/tabbar/home?lang=ja',
            'https://shortmax.app/tabbar/home?locale=ja',
            'https://shortmax.app/ja/tabbar/home',
            'https://shortmax.app/tabbar/home?language=ja',
            'https://shortmax.app/tabbar/home?hl=ja',
        ]
        return japanese_urls
    
    def scrape_japanese_pages(self) -> List[Dict[str, str]]:
        """日本語ページをスクレイピング"""
        all_works = []
        japanese_urls = self.get_japanese_urls()
        
        for i, url in enumerate(japanese_urls):
            try:
                self.logger.info(f"Scraping Japanese page {i+1}/{len(japanese_urls)}: {url}")
                self.driver.get(url)
                time.sleep(5)
                self.wait_for_page_load()
                
                # 日本語ページ用のスクロール
                for scroll in range(30):
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                
                japanese_works = self.extract_work_data_from_elements(f"Japanese Page {i+1}")
                all_works.extend(japanese_works)
                self.logger.info(f"Extracted {len(japanese_works)} works from Japanese page {i+1}")
                
            except Exception as e:
                self.logger.warning(f"Error scraping Japanese page {url}: {e}")
                continue
        
        return all_works
    
    def scrape_parallel_sections(self, urls: List[str]) -> List[Dict[str, str]]:
        """並列でセクションをスクレイピング（順次実行に変更）"""
        all_works = []
        
        for i, url in enumerate(urls):
            try:
                self.logger.info(f"Scraping section {i+1}/{len(urls)}: {url}")
                works = self.scrape_single_section(url, f"Section {i+1}")
                all_works.extend(works)
                self.logger.info(f"Completed scraping {url}: {len(works)} works")
            except Exception as e:
                self.logger.error(f"Error scraping {url}: {e}")
        
        return all_works
    
    def scrape_single_section(self, url: str, section_name: str) -> List[Dict[str, str]]:
        """単一セクションをスクレイピング"""
        works = []
        try:
            self.driver.get(url)
            time.sleep(3)
            self.wait_for_page_load()
            self.scroll_and_load_content()
            works = self.extract_work_data_from_elements(section_name)
        except Exception as e:
            self.logger.error(f"Error scraping section {url}: {e}")
        
        return works
    
    async def scrape_individual_work_details_async(self, work_url: str) -> Dict:
        """非同期で個別作品詳細をスクレイピング"""
        additional_data = {
            'episode_count': '',
            'detailed_description': '',
            'favorite_count': '',
            'comments_count': '',
            'rating': '',
            'duration': '',
            'release_date': ''
        }
        
        if work_url in self.scraped_urls:
            return additional_data
            
        try:
            async with self.session.get(work_url) as response:
                if response.status == 200:
                    html = await response.text()
                    # HTMLから詳細情報を抽出
                    additional_data.update(self.parse_work_details_from_html(html))
                    self.scraped_urls.add(work_url)
        except Exception as e:
            self.logger.warning(f"Error scraping individual work details from {work_url}: {e}")
        
        return additional_data
    
    def parse_work_details_from_html(self, html: str) -> Dict[str, str]:
        """HTMLから作品詳細を解析"""
        details = {}
        
        try:
            # エピソード数の抽出
            episode_match = re.search(r'(\d+)\s*(?:Episode|episode|エピソード)', html, re.IGNORECASE)
            if episode_match:
                details['episode_count'] = episode_match.group(1)
            
            # お気に入り数の抽出
            favorite_match = re.search(r'(\d+(?:\.\d+)?[KM]?)\s*(?:favorites?|likes?|お気に入り|いいね)', html, re.IGNORECASE)
            if favorite_match:
                details['favorite_count'] = favorite_match.group(1)
            
            # コメント数の抽出
            comment_match = re.search(r'(\d+(?:\.\d+)?[KM]?)\s*(?:comments?|コメント)', html, re.IGNORECASE)
            if comment_match:
                details['comments_count'] = comment_match.group(1)
            
            # 評価の抽出
            rating_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:stars?|星|rating)', html, re.IGNORECASE)
            if rating_match:
                details['rating'] = rating_match.group(1)
            
            # 再生時間の抽出
            duration_match = re.search(r'(\d+(?::\d+)*)\s*(?:min|minutes?|分)', html, re.IGNORECASE)
            if duration_match:
                details['duration'] = duration_match.group(1)
            
            # リリース日の抽出
            date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', html)
            if date_match:
                details['release_date'] = date_match.group(1)
            
        except Exception as e:
            self.logger.warning(f"Error parsing work details from HTML: {e}")
        
        return details
    
    def remove_duplicates(self):
        """重複を削除（改良版）"""
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
                'every moment', 'user agreement', 'privacy policy',
                'インストール', 'ダウンロード', 'サインイン', 'ボーナス', '分類',
                'ホーム', 'ショート', 'マイリスト', 'プロフィール', '検索',
                '毎瞬間', 'ユーザー規約', 'プライバシーポリシー'
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
        """再生数文字列を数値に変換"""
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
    
    def export_to_csv(self, filename: str = "enhanced_shortmax_works_data.csv"):
        """CSVにエクスポート（改良版）"""
        try:
            if not self.all_works_data:
                self.logger.warning("No data to export")
                return None
            
            df = pd.DataFrame(self.all_works_data)
            
            # 必要な列を定義
            required_columns = [
                'title', 'view_count', 'favorite_count', 'synopsis', 'section', 
                'category', 'tags', 'episode_count', 'detailed_description', 
                'comments_count', 'rating', 'duration', 'release_date',
                'url', 'scrape_timestamp'
            ]
            
            for col in required_columns:
                if col not in df.columns:
                    df[col] = ''
            
            df = df[required_columns]
            
            df.to_csv(filename, index=False, encoding='utf-8')
            self.logger.info(f"Data exported to {filename}")
            self.logger.info(f"Total works exported: {len(df)}")
            
            return filename
            
        except Exception as e:
            self.logger.error(f"Error exporting to CSV: {e}")
            return None
    
    async def run_enhanced_scraper(self):
        """改良されたスクレイパーを実行"""
        try:
            self.setup_driver()
            await self.setup_session()
            
            self.logger.info("Starting enhanced Japanese scraper with parallel processing")
            
            all_works = []
            
            # Phase 1: 日本語ページのスクレイピング
            self.logger.info("=== PHASE 1: Scraping Japanese pages ===")
            japanese_works = self.scrape_japanese_pages()
            all_works.extend(japanese_works)
            self.logger.info(f"Phase 1 complete: {len(japanese_works)} works from Japanese pages")
            
            # Phase 2: 並列でセクションをスクレイピング
            self.logger.info("=== PHASE 2: Parallel section scraping ===")
            urls_to_scrape = [
                'https://shortmax.app/tabbar/home',
                'https://shortmax.app/tabbar/home?sort=popular',
                'https://shortmax.app/tabbar/home?sort=newest',
                'https://shortmax.app/tabbar/home?category=all',
                'https://shortmax.app/tabbar/home?filter=trending'
            ]
            
            parallel_works = self.scrape_parallel_sections(urls_to_scrape)
            all_works.extend(parallel_works)
            self.logger.info(f"Phase 2 complete: {len(parallel_works)} works from parallel scraping")
            
            # Phase 3: 重複削除
            self.logger.info("=== PHASE 3: Removing duplicates ===")
            self.all_works_data = all_works
            self.remove_duplicates()
            self.logger.info(f"Phase 3 complete: {len(self.all_works_data)} unique works")
            
            # Phase 4: 個別作品詳細の取得（簡略化）
            self.logger.info("=== PHASE 4: Enhancing with individual details ===")
            # 最初の20作品のみ詳細取得（パフォーマンス向上のため）
            for i, work in enumerate(self.all_works_data[:20]):
                if work['title'] and len(work['title']) > 3:
                    try:
                        individual_url = f"https://shortmax.app/search?q={work['title'].replace(' ', '+')}"
                        additional_data = await self.scrape_individual_work_details_async(individual_url)
                        work.update(additional_data)
                    except Exception as e:
                        self.logger.warning(f"Error enhancing work {work['title']}: {e}")
                        continue
            
            # Phase 5: エクスポート
            self.logger.info("=== PHASE 5: Exporting results ===")
            csv_file = self.export_to_csv()
            
            self.logger.info("Enhanced scraping completed successfully")
            return csv_file
            
        except Exception as e:
            self.logger.error(f"Error in run_enhanced_scraper: {e}")
            return None
            
        finally:
            if self.driver:
                self.driver.quit()
                self.logger.info("Driver closed")
            await self.close_session()

def run_enhanced_japanese_scraper():
    """改良された日本語スクレイパーを実行"""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    scraper = EnhancedJapaneseScraper(max_workers=4)
    
    try:
        # 非同期実行
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        csv_file = loop.run_until_complete(scraper.run_enhanced_scraper())
        
        if csv_file:
            print(f"\n🎉 SUCCESS: Enhanced scraping completed!")
            print(f"📊 Results exported to: {csv_file}")
            print(f"📈 Total unique works found: {len(scraper.all_works_data)}")
            
            # 結果の分析
            if scraper.all_works_data:
                sorted_works = sorted(scraper.all_works_data, 
                                    key=lambda x: scraper.parse_view_count_to_number(x['view_count']), 
                                    reverse=True)
                
                print("\n📊 Top 10 works by view count:")
                for i, work in enumerate(sorted_works[:10]):
                    print(f"{i+1}. \"{work['title']}\" - {work['view_count']} views - {work.get('favorite_count', 'N/A')} favorites")
                
                # 統計情報
                high_view_works = [w for w in scraper.all_works_data if scraper.parse_view_count_to_number(w['view_count']) > 100000]
                medium_view_works = [w for w in scraper.all_works_data if 10000 < scraper.parse_view_count_to_number(w['view_count']) <= 100000]
                low_view_works = [w for w in scraper.all_works_data if scraper.parse_view_count_to_number(w['view_count']) <= 10000]
                
                print(f"\n📈 View count analysis:")
                print(f"High view count (>100K): {len(high_view_works)} works")
                print(f"Medium view count (10K-100K): {len(medium_view_works)} works")
                print(f"Low view count (≤10K): {len(low_view_works)} works")
                
                # セクション分布
                section_counts = {}
                for work in scraper.all_works_data:
                    sec = work.get('section', 'Unknown')
                    section_counts[sec] = section_counts.get(sec, 0) + 1
                
                print(f"\n📊 Section distribution:")
                for sec, count in sorted(section_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                    print(f"{sec}: {count} works")
        
        return csv_file
        
    except Exception as e:
        print(f"❌ Error running enhanced scraper: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    run_enhanced_japanese_scraper()