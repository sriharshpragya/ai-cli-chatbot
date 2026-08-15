# ============================================
# tools/file_reader.py
# Safe file reading tool
# ============================================
import os
from pathlib import Path
from typing import Optional
import structlog

logger = structlog.get_logger()


# ============================================
# CONFIGURATION
# ============================================

MAX_FILE_SIZE_MB = 5  # Don't read files larger than 5MB
MAX_CONTENT_LENGTH = 5000  # Truncate content to 5000 chars

# Allowed extensions for safety
SAFE_EXTENSIONS = {
    # Text
    '.txt', '.md', '.rst',
    # Config
    '.json', '.yaml', '.yml', '.toml', '.ini', '.env', '.cfg',
    # Code
    '.py', '.js', '.ts', '.jsx', '.tsx', '.rb', '.go', '.rs',
    '.java', '.cpp', '.c', '.h', '.cs', '.php', '.swift',
    # Web
    '.html', '.css', '.scss', '.sass',
    # Data
    '.csv', '.tsv', '.xml', '.log',
    # Scripts
    '.sh', '.bash', '.zsh',
    # Docs
    '.mdx', '.tex',
    # No extension (README, LICENSE, etc.)
    '',
}


# ============================================
# HELPER FUNCTIONS
# ============================================

def _is_safe_path(file_path: str) -> tuple[bool, str]:
    """
    Check if the file path is safe to read.
    Returns (is_safe, error_message).
    """
    # Convert to Path object
    try:
        path = Path(file_path).expanduser().resolve()
    except Exception as e:
        return False, f"Invalid path: {str(e)}"
    
    # Must be a file
    if not path.exists():
        return False, f"File not found: {file_path}"
    
    if not path.is_file():
        return False, f"Not a file: {file_path}"
    
    # Check size
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        return False, f"File too large ({size_mb:.1f}MB). Max: {MAX_FILE_SIZE_MB}MB"
    
    # Check extension (allow README, LICENSE, etc. with no extension)
    ext = path.suffix.lower()
    if ext and ext not in SAFE_EXTENSIONS:
        return False, f"File type not allowed: {ext}"
    
    return True, ""


def _is_binary(file_path: str) -> bool:
    """
    Check if file is binary by reading first 8KB.
    Binary files typically contain null bytes.
    """
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(8192)
            if b'\0' in chunk:
                return True
        return False
    except Exception:
        return True  # If we can't read, assume binary


# ============================================
# THE TOOL
# ============================================

def read_file(file_path: str, max_chars: Optional[int] = None) -> dict:
    """
    Read contents of a text file safely.
    
    Args:
        file_path: Path to file (supports ~ for home directory)
        max_chars: Maximum characters to return (default: 5000)
    
    Returns:
        dict with file content or error info
    """
    logger.info("read_file_requested", file_path=file_path)
    
    # Use default max_chars if not specified
    if max_chars is None:
        max_chars = MAX_CONTENT_LENGTH
    
    # Cap max_chars to prevent abuse
    max_chars = min(max_chars, MAX_CONTENT_LENGTH * 2)
    
    # Safety checks
    is_safe, error_msg = _is_safe_path(file_path)
    if not is_safe:
        logger.warning("unsafe_file_path", file_path=file_path, error=error_msg)
        return {
            "error": "unsafe_path",
            "message": error_msg,
        }
    
    # Resolve path
    path = Path(file_path).expanduser().resolve()
    
    # Check if binary
    if _is_binary(str(path)):
        return {
            "error": "binary_file",
            "message": "Cannot read binary files. This tool only supports text files.",
            "file_path": str(path),
        }
    
    # Read the file
    try:
        # Try UTF-8 first (most common)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            # Fall back to latin-1 (always succeeds)
            with open(path, 'r', encoding='latin-1') as f:
                content = f.read()
        
        original_length = len(content)
        truncated = False
        
        if original_length > max_chars:
            content = content[:max_chars] + f"\n\n... [TRUNCATED: showing {max_chars} of {original_length} chars]"
            truncated = True
        
        logger.info(
            "file_read_successfully",
            file_path=str(path),
            size=original_length,
            truncated=truncated,
        )
        
        return {
            "file_path": str(path),
            "filename": path.name,
            "extension": path.suffix,
            "size_bytes": path.stat().st_size,
            "content": content,
            "original_length": original_length,
            "truncated": truncated,
            "lines": content.count('\n') + 1,
        }
    
    except PermissionError:
        logger.error("permission_denied", file_path=file_path)
        return {
            "error": "permission_denied",
            "message": f"No permission to read: {file_path}",
        }
    
    except Exception as e:
        logger.error("read_file_error", file_path=file_path, error=str(e))
        return {
            "error": "read_error",
            "message": f"Could not read file: {str(e)}",
        }


# ============================================
# TOOL SCHEMA FOR LLM
# ============================================

read_file_schema = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Read the contents of a text file from the local filesystem. "
            "Supports text files like .txt, .md, .json, .py, .js, .yaml, config files, etc. "
            "Cannot read binary files (images, PDFs, executables). "
            "Uses ~ for home directory. Content truncated if too large."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Full path to the file (e.g., '~/documents/notes.md', '/etc/hosts', './README.md')"
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return (default: 5000, max: 10000)",
                    "minimum": 100,
                    "maximum": 10000,
                }
            },
            "required": ["file_path"]
        }
    }
}


# ============================================
# DIRECT TEST
# ============================================

if __name__ == "__main__":
    import json
    
    # Test cases
    test_cases = [
        # Test 1: Read this file
        "~/ai-learning-journal/practice/week5/day32/tools/file_reader.py",
        
        # Test 2: Nonexistent file
        "/nonexistent/file.txt",
        
        # Test 3: Binary file (should reject)
        "/bin/ls",  # Binary on Mac/Linux
        
        # Test 4: Common config
        "~/.bashrc",  # May or may not exist
    ]
    
    for path in test_cases:
        print("=" * 60)
        print(f"Testing: {path}")
        print("=" * 60)
        
        result = read_file(path, max_chars=200)
        
        # Truncate content for display
        if "content" in result:
            content = result["content"][:200]
            result["content"] = content + "..." if len(content) == 200 else content
        
        print(json.dumps(result, indent=2))
        print()

# OUTPUT:

# ============================================================
# Testing: ~/ai-learning-journal/practice/week5/day32/tools/file_reader.py
# ============================================================
# 2026-08-14 17:55:08 [info     ] read_file_requested            file_path=~/ai-learning-journal/practice/week5/day32/tools/file_reader.py
# 2026-08-14 17:55:08 [warning  ] unsafe_file_path               error='File not found: ~/ai-learning-journal/practice/week5/day32/tools/file_reader.py' file_path=~/ai-learning-journal/practice/week5/day32/tools/file_reader.py
# {
#   "error": "unsafe_path",
#   "message": "File not found: ~/ai-learning-journal/practice/week5/day32/tools/file_reader.py"
# }

# ============================================================
# Testing: /nonexistent/file.txt
# ============================================================
# 2026-08-14 17:55:08 [info     ] read_file_requested            file_path=/nonexistent/file.txt
# 2026-08-14 17:55:08 [warning  ] unsafe_file_path               error='File not found: /nonexistent/file.txt' file_path=/nonexistent/file.txt
# {
#   "error": "unsafe_path",
#   "message": "File not found: /nonexistent/file.txt"
# }

# ============================================================
# Testing: /bin/ls
# ============================================================
# 2026-08-14 17:55:08 [info     ] read_file_requested            file_path=/bin/ls
# {
#   "error": "binary_file",
#   "message": "Cannot read binary files. This tool only supports text files.",
#   "file_path": "/bin/ls"
# }

# ============================================================
# Testing: ~/.bashrc
# ============================================================
# 2026-08-14 17:55:08 [info     ] read_file_requested            file_path=~/.bashrc
# 2026-08-14 17:55:08 [warning  ] unsafe_file_path               error='File not found: ~/.bashrc' file_path=~/.bashrc
# {
#   "error": "unsafe_path",
#   "message": "File not found: ~/.bashrc"
# }
