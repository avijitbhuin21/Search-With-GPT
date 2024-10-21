import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List
from urllib.parse import urlparse, urljoin, quote_plus
import html2text
import json

DEBUG = False  # Set to True for debugging

def log_debug(message):
    if DEBUG:
        print(f"DEBUG: {message}")


class Research_Tool:
    def __init__(self, max_depth: int = 3, max_pages: int = 100, max_tokens: int = 4096):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.html2text_converter = html2text.HTML2Text()
        self.html2text_converter.ignore_links = False
        self.html2text_converter.ignore_images = False
        self.html2text_converter.ignore_emphasis = False
        self.html2text_converter.body_width = 0 
        self.max_tokens = max_tokens
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,/;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

    def scrape_page(self, url: str, header_disabled = False, Get_Soup = False) -> Dict[str, Any]:
        try:
            if header_disabled:
                response = requests.get(url, timeout=5)
            else:
                response = requests.get(url, headers=self.headers, timeout=5)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')

            result = {
                'url': url,
                'metadata': self.extract_metadata(soup, url),
            }
            result['structured_data'] = self.extract_structured_data(soup)
            if Get_Soup:
                return (response.text, result)
            return ("", result)
        except requests.RequestException as e:
            try:
                return self.scrape_page(url=url, header_disabled=True, timeout=5)
            except:
                print(f"Error scraping {url}: {str(e)}")
                return None
            return None

    def extract_links(self, base_url: str, html_content: str) -> List[str]:
        soup = BeautifulSoup(html_content, 'html.parser')
        base_domain = urlparse(base_url).netloc
        links = []

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            full_url = urljoin(base_url, href)
            if urlparse(full_url).netloc == base_domain:
                links.append(full_url)

        return links

    def extract_metadata(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        metadata = {
            'title': soup.title.string if soup.title else '',
            'description': '',
            'language': soup.html.get('lang', ''),
            'sourceURL': url,
        }

        meta_tags = soup.find_all('meta')
        for tag in meta_tags:
            if tag.get('name') == 'description':
                metadata['description'] = tag.get('content', '')
            elif tag.get('property') == 'og:description':
                metadata['og_description'] = tag.get('content', '')

        return metadata
    def extract_relevant_text(self, soup: BeautifulSoup) -> str:
        try:
            extracted_text = []
            target_tags = ["h1", "h2", "h3", "h4", "h5", "p", "li", "div", "span"]

            for element in soup.find_all(target_tags):
                if not element.text.strip():
                    continue
                if len(element.text.split()) < 3:
                    continue
                if any(cls in ['nav', 'menu', 'sidebar', 'footer'] for cls in element.parent.get('class', [])):
                    continue
                cleaned_text = ' '.join(element.text.split())
                extracted_text.append(cleaned_text)
            
            data ='\n\n'.join(extracted_text)
            return data
        except:
            return soup.text


    def extract_structured_data(self, soup: BeautifulSoup) -> Dict[str, Any]:
        structured_data = {}

        # Extract all text content
        all_text = self.extract_relevant_text(soup)
        structured_data['full_text'] = all_text

        # Extract headings
        headings = {}
        for i in range(1, 7):
            h_tags = soup.find_all(f'h{i}')
            if h_tags:
                headings[f'h{i}'] = [tag.get_text(strip=True) for tag in h_tags]
        structured_data['headings'] = headings

        # Extract links
        links = []
        for a in soup.find_all('a', href=True):
            links.append({
                'text': a.get_text(strip=True),
                'href': a['href']
            })
        structured_data['links'] = links

        # Extract images
        images = []
        for img in soup.find_all('img', src=True):
            images.append({
                'src': img['src'],
                'alt': img.get('alt', '')
            })
        structured_data['images'] = images

        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                structured_data['json_ld'] = data
            except json.JSONDecodeError:
                pass

        return structured_data

    def search(self, query: str, no_of_results: int) -> List[Dict[str, Any]]:
        log_debug(f"Performing web search for: {query}")
        search_results = self._perform_web_search(query, no_of_results)
        filtered_results = self._filter_search_results(search_results)
        deduplicated_results = self._remove_duplicates(filtered_results)
        log_debug(f"Found {len(deduplicated_results)} unique results")
        return deduplicated_results[:no_of_results]

    def _perform_web_search(self, query: str, no_of_results: int) -> List[Dict[str, Any]]:
        encoded_query = quote_plus(query)
        search_url = f"https://www.google.com/search?q={encoded_query}&num={no_of_results * 2}"
        log_debug(f"Search URL: {search_url}")
        
        try:
            log_debug("Sending GET request to Google")
            response = requests.get(search_url, headers=self.headers, timeout=5)
            log_debug(f"Response status code: {response.status_code}")
            response.raise_for_status()
            
            log_debug("Parsing HTML with BeautifulSoup")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            log_debug("Searching for result divs")
            search_results = []
            for g in soup.find_all('div', class_='g'):
                log_debug("Processing a search result div")
                anchor = g.find('a')
                title = g.find('h3').text if g.find('h3') else 'No title'
                url = anchor.get('href', 'No URL') if anchor else 'No URL'
                
                description = ''
                description_div = g.find('div', class_=['VwiC3b', 'yXK7lf'])
                if description_div:
                    description = description_div.get_text(strip=True)
                else:
                    description = g.get_text(strip=True)
                
                log_debug(f"Found result: Title: {title[:30]}..., URL: {url[:30]}...")
                search_results.append({
                    'title': title,
                    'description': description,
                    'url': url
                })
            
            log_debug(f"Successfully retrieved {len(search_results)} search results for query: {query}")
            return search_results
        except requests.RequestException as e:
            log_debug(f"Error performing search: {str(e)}")
            return []

    def _filter_search_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        filtered = [result for result in results if result['description'] and result['title'] != 'No title' and result['url'].startswith('https://')]
        log_debug(f"Filtered to {len(filtered)} results")
        return filtered

    def _remove_duplicates(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen_urls = set()
        unique_results = []
        for result in results:
            if result['url'] not in seen_urls:
                seen_urls.add(result['url'])
                unique_results.append(result)
        log_debug(f"Removed duplicates, left with {len(unique_results)} results")
        return unique_results

