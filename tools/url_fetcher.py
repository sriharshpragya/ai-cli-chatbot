# ============================================
# tools/url_fetcher.py
# Safe URL fetching tool
# ============================================
import requests
from urllib.parse import urlparse
from typing import Optional
from bs4 import BeautifulSoup
import structlog

logger = structlog.get_logger()


# ============================================
# CONFIGURATION
# ============================================

REQUEST_TIMEOUT = 10  # seconds
MAX_CONTENT_SIZE_MB = 10  # Max response size
MAX_TEXT_LENGTH = 5000  # Max text characters returned

# Allowed content types
ALLOWED_CONTENT_TYPES = {
    'text/html',
    'text/plain',
    'application/json',
    'application/xml',
    'text/xml',
    'text/markdown',
}

# Standard headers - identify as browser
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; PersonalAssistantAgent/1.0)',
    'Accept': 'text/html,application/xhtml+xml,application/xml,text/plain',
    'Accept-Language': 'en-US,en;q=0.9',
}


# ============================================
# HELPER FUNCTIONS
# ============================================

def _validate_url(url: str) -> tuple[bool, str]:
    """
    Validate URL is safe to fetch.
    Returns (is_valid, error_message).
    """
    if not url:
        return False, "URL is empty"
    
    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {str(e)}"
    
    # Must have scheme
    if parsed.scheme not in ('http', 'https'):
        return False, f"URL must use http or https (got: {parsed.scheme})"
    
    # Must have domain
    if not parsed.netloc:
        return False, "URL missing domain"
    
    # Block localhost and internal IPs (security)
    blocked_hosts = {
        'localhost',
        '127.0.0.1',
        '0.0.0.0',
        '169.254.169.254',  # AWS metadata
    }
    
    if parsed.netloc.lower() in blocked_hosts:
        return False, f"Cannot fetch internal URLs: {parsed.netloc}"
    
    # Block private IPs
    hostname = parsed.hostname or ""
    if (
        hostname.startswith('192.168.') or
        hostname.startswith('10.') or
        hostname.startswith('172.16.') or
        hostname.startswith('172.17.') or
        hostname.startswith('172.18.') or
        hostname.startswith('172.19.') or
        hostname.startswith('172.20.')
    ):
        return False, f"Cannot fetch private IP: {hostname}"
    
    return True, ""


def _extract_text_from_html(html: str) -> str:
    """Extract clean text from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove script and style elements
    for element in soup(['script', 'style', 'nav', 'footer', 'header']):
        element.decompose()
    
    # Get title
    title = soup.title.string if soup.title else ""
    
    # Get main text
    text = soup.get_text(separator='\n', strip=True)
    
    # Clean up whitespace
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    clean_text = '\n'.join(lines)
    
    if title:
        return f"TITLE: {title}\n\n{clean_text}"
    return clean_text


# ============================================
# THE TOOL
# ============================================

def fetch_url(
    url: str,
    max_chars: Optional[int] = None,
    extract_text: bool = True,
) -> dict:
    """
    Fetch content from a URL safely.
    
    Args:
        url: URL to fetch (must be http:// or https://)
        max_chars: Maximum characters in returned content
        extract_text: If True and content is HTML, extract text only
    
    Returns:
        dict with content or error info
    """
    logger.info("fetch_url_requested", url=url)
    
    # Use default max_chars if not specified
    if max_chars is None:
        max_chars = MAX_TEXT_LENGTH
    
    # Cap max_chars
    max_chars = min(max_chars, MAX_TEXT_LENGTH * 2)
    
    # Validate URL
    is_valid, error_msg = _validate_url(url)
    if not is_valid:
        logger.warning("invalid_url", url=url, error=error_msg)
        return {
            "error": "invalid_url",
            "message": error_msg,
        }
    
    # Fetch the URL
    try:
        response = requests.get(
            url,
            headers=DEFAULT_HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            stream=True,  # For size checking
        )
        
        # Check status
        if response.status_code >= 400:
            logger.warning(
                "url_fetch_failed",
                url=url,
                status=response.status_code,
            )
            return {
                "error": "http_error",
                "status_code": response.status_code,
                "message": f"HTTP {response.status_code}: {response.reason}",
                "url": response.url,
            }
        
        # Check content-type
        content_type = response.headers.get('content-type', '').split(';')[0].strip().lower()
        
        if content_type and not any(
            allowed in content_type for allowed in ALLOWED_CONTENT_TYPES
        ):
            return {
                "error": "unsupported_content_type",
                "content_type": content_type,
                "message": f"Cannot process content type: {content_type}",
            }
        
        # Check size before downloading
        content_length = response.headers.get('content-length')
        if content_length:
            size_mb = int(content_length) / (1024 * 1024)
            if size_mb > MAX_CONTENT_SIZE_MB:
                return {
                    "error": "response_too_large",
                    "size_mb": size_mb,
                    "message": f"Response too large ({size_mb:.1f}MB). Max: {MAX_CONTENT_SIZE_MB}MB",
                }
        
        # Download content (with size limit)
        content_bytes = b""
        max_bytes = MAX_CONTENT_SIZE_MB * 1024 * 1024
        for chunk in response.iter_content(chunk_size=8192):
            content_bytes += chunk
            if len(content_bytes) > max_bytes:
                return {
                    "error": "response_too_large",
                    "message": f"Response exceeded {MAX_CONTENT_SIZE_MB}MB",
                }
        
        # Decode
        try:
            content = content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            content = content_bytes.decode('latin-1', errors='ignore')
        
        # Extract text if HTML
        if extract_text and 'html' in content_type:
            content = _extract_text_from_html(content)
        
        # Truncate if needed
        original_length = len(content)
        truncated = False
        
        if original_length > max_chars:
            content = content[:max_chars] + f"\n\n... [TRUNCATED: showing {max_chars} of {original_length} chars]"
            truncated = True
        
        logger.info(
            "url_fetched_successfully",
            url=url,
            content_type=content_type,
            size=original_length,
            truncated=truncated,
        )
        
        return {
            "url": response.url,  # Final URL after redirects
            "status_code": response.status_code,
            "content_type": content_type,
            "content": content,
            "original_length": original_length,
            "truncated": truncated,
        }
    
    except requests.Timeout:
        logger.error("url_fetch_timeout", url=url)
        return {
            "error": "timeout",
            "message": f"Request timed out after {REQUEST_TIMEOUT}s",
        }
    
    except requests.ConnectionError as e:
        logger.error("url_fetch_connection_error", url=url, error=str(e))
        return {
            "error": "connection_error",
            "message": f"Could not connect: {str(e)}",
        }
    
    except Exception as e:
        logger.error("url_fetch_error", url=url, error=str(e))
        return {
            "error": "fetch_error",
            "message": f"Unexpected error: {str(e)}",
        }


# ============================================
# TOOL SCHEMA FOR LLM
# ============================================

fetch_url_schema = {
    "type": "function",
    "function": {
        "name": "fetch_url",
        "description": (
            "Fetch content from a URL (webpage, JSON API, text file, etc.). "
            "For HTML pages, extracts main text content. "
            "Supports http:// and https:// URLs only. "
            "Content is truncated if too large. Cannot fetch binary files."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch (must start with http:// or https://)"
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return (default 5000, max 10000)",
                    "minimum": 100,
                    "maximum": 10000,
                },
                "extract_text": {
                    "type": "boolean",
                    "description": "If True, extract text from HTML (default: True)"
                }
            },
            "required": ["url"]
        }
    }
}


# ============================================
# DIRECT TEST
# ============================================

if __name__ == "__main__":
    import json
    
    test_cases = [
        # Test 1: Simple public API
        "https://api.github.com/zen",
        
        # Test 2: HTML webpage
        "https://example.com",
        
        # Test 3: Invalid URL
        "not-a-url",
        
        # Test 4: Localhost (should reject)
        "http://localhost:8080",
        
        # Test 5: Public JSON
        "https://api.publicapis.org/entries?limit=3",
    ]
    
    for url in test_cases:
        print("=" * 60)
        print(f"Testing: {url}")
        print("=" * 60)
        
        result = fetch_url(url, max_chars=300)
        
        # Truncate content for display
        if "content" in result:
            content = result["content"][:300]
            result["content"] = content + "..." if len(content) == 300 else content
        
        print(json.dumps(result, indent=2))
        print()
        