import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from langchain_community.document_loaders import PlaywrightURLLoader
from langchain_core.documents import Document

def valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

def fetch_website_html(url: str):
    try:
        loader = PlaywrightURLLoader(urls=[url])
        docs = loader.load()
        return docs[0].page_content
    except Exception:
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            return BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
        except Exception:
            return None

def crawl_links(start_url, limit=10):
    """Crawl a website and return internal links up to a limit."""
    visited = set()
    to_visit = [start_url]
    all_links = []

    while to_visit and len(all_links) < limit:
        url = to_visit.pop()
        if url in visited:
            continue
        visited.add(url)
        try:
            r = requests.get(url, timeout=5)
            soup = BeautifulSoup(r.text, "html.parser")
            all_links.append(url)

            for link in soup.find_all("a", href=True):
                href = link["href"]
                if href.startswith("/"):
                    href = start_url.rstrip("/") + href
                if href.startswith(start_url) and href not in visited:
                    to_visit.append(href)
        except Exception as e:
            print(f"Skipping {url} -> {e}")
    return all_links