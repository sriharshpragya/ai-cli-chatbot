# ============================================
# GitHub Tools for Agent
# ============================================
import os
import requests
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import structlog

logger = structlog.get_logger()

BASE_URL = "https://api.github.com"


def _get_headers():
    """Get authenticated headers."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise Exception("GITHUB_TOKEN not set in environment")
    
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


class GitHubAPIError(Exception):
    """GitHub API error - permanent, don't retry."""
    pass


class GitHubTransientError(Exception):
    """Transient error - retry with backoff."""
    pass


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(GitHubTransientError),
    reraise=True,  # From Day 29 fix!
)
def _github_request(endpoint: str, params: dict = None) -> dict:
    """Make authenticated GitHub API request with retry."""
    try:
        response = requests.get(
            f"{BASE_URL}{endpoint}",
            headers=_get_headers(),
            params=params,
            timeout=10,  # Don't hang forever
        )
    except requests.Timeout:
        raise GitHubTransientError("GitHub API timeout")
    except requests.ConnectionError:
        raise GitHubTransientError("Connection error")
    
    # Handle response
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 404:
        raise GitHubAPIError("Resource not found")
    elif response.status_code == 401:
        raise GitHubAPIError("Authentication failed - check GITHUB_TOKEN")
    elif response.status_code == 403:
        # Could be rate limit or permission
        if "rate limit" in response.text.lower():
            raise GitHubAPIError("Rate limit exceeded")
        raise GitHubAPIError("Permission denied")
    elif response.status_code >= 500:
        raise GitHubTransientError(f"GitHub server error: {response.status_code}")
    else:
        raise GitHubAPIError(f"Unexpected status: {response.status_code}")


# ============================================
# TOOL 1: List User Repositories
# ============================================

def list_user_repos(username: str, max_results: int = 10) -> dict:
    """List public repositories for a GitHub user."""
    logger.info("listing_repos", username=username)
    
    try:
        repos = _github_request(
            f"/users/{username}/repos",
            params={"per_page": max_results, "sort": "updated"}
        )
        
        # Simplify data for LLM
        simplified = [
            {
                "name": repo["name"],
                "description": repo.get("description") or "No description",
                "language": repo.get("language") or "Unknown",
                "stars": repo["stargazers_count"],
                "forks": repo["forks_count"],
                "updated_at": repo["updated_at"],
                "url": repo["html_url"],
                "open_issues": repo["open_issues_count"],
            }
            for repo in repos
        ]
        
        return {
            "username": username,
            "total_shown": len(simplified),
            "repos": simplified,
        }
    
    except GitHubAPIError as e:
        return {"error": "github_api_error", "message": str(e)}
    except GitHubTransientError as e:
        return {"error": "temporary_error", "message": str(e), "retry_after": 30}


list_repos_schema = {
    "type": "function",
    "function": {
        "name": "list_user_repos",
        "description": "List public GitHub repositories for a user. Returns repo name, description, language, stars, forks, and update time.",
        "parameters": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "GitHub username (e.g., 'openai', 'sriharshpragya')"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of repos to return (default 10)",
                    "minimum": 1,
                    "maximum": 100,
                }
            },
            "required": ["username"]
        }
    }
}


# ============================================
# TOOL 2: Get Repository Issues
# ============================================

def get_repo_issues(
    owner: str,
    repo: str,
    state: str = "open",
    max_results: int = 10,
) -> dict:
    """Get issues from a GitHub repository."""
    logger.info("getting_issues", owner=owner, repo=repo, state=state)
    
    try:
        issues = _github_request(
            f"/repos/{owner}/{repo}/issues",
            params={"state": state, "per_page": max_results}
        )
        
        # Filter out pull requests (they show up in issues endpoint)
        actual_issues = [i for i in issues if "pull_request" not in i]
        
        # Simplify data
        simplified = [
            {
                "number": issue["number"],
                "title": issue["title"],
                "state": issue["state"],
                "author": issue["user"]["login"],
                "labels": [label["name"] for label in issue.get("labels", [])],
                "comments": issue["comments"],
                "created_at": issue["created_at"],
                "url": issue["html_url"],
            }
            for issue in actual_issues
        ]
        
        return {
            "owner": owner,
            "repo": repo,
            "state": state,
            "total_shown": len(simplified),
            "issues": simplified,
        }
    
    except GitHubAPIError as e:
        return {"error": "github_api_error", "message": str(e)}
    except GitHubTransientError as e:
        return {"error": "temporary_error", "message": str(e)}


get_issues_schema = {
    "type": "function",
    "function": {
        "name": "get_repo_issues",
        "description": "Get issues from a GitHub repository. Returns issue number, title, state, author, labels, and comment count.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {
                    "type": "string",
                    "description": "Repository owner username (e.g., 'openai')"
                },
                "repo": {
                    "type": "string",
                    "description": "Repository name (e.g., 'openai-python')"
                },
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "description": "Issue state filter (default: open)"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of issues to return (default 10)",
                    "minimum": 1,
                    "maximum": 100,
                }
            },
            "required": ["owner", "repo"]
        }
    }
}


# ============================================
# TOOL 3: Get Repository Details
# ============================================

def get_repo_details(owner: str, repo: str) -> dict:
    """Get detailed information about a GitHub repository."""
    logger.info("getting_repo_details", owner=owner, repo=repo)
    
    try:
        info = _github_request(f"/repos/{owner}/{repo}")
        
        return {
            "name": info["name"],
            "full_name": info["full_name"],
            "description": info.get("description") or "No description",
            "language": info.get("language") or "Unknown",
            "stars": info["stargazers_count"],
            "forks": info["forks_count"],
            "open_issues": info["open_issues_count"],
            "watchers": info["subscribers_count"],
            "size_kb": info["size"],
            "default_branch": info["default_branch"],
            "created_at": info["created_at"],
            "updated_at": info["updated_at"],
            "url": info["html_url"],
            "topics": info.get("topics", []),
            "license": info.get("license", {}).get("name") if info.get("license") else None,
        }
    
    except GitHubAPIError as e:
        return {"error": "github_api_error", "message": str(e)}
    except GitHubTransientError as e:
        return {"error": "temporary_error", "message": str(e)}


get_repo_schema = {
    "type": "function",
    "function": {
        "name": "get_repo_details",
        "description": "Get detailed information about a specific GitHub repository including stars, forks, language, topics, and license.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {
                    "type": "string",
                    "description": "Repository owner username"
                },
                "repo": {
                    "type": "string",
                    "description": "Repository name"
                }
            },
            "required": ["owner", "repo"]
        }
    }
}


# ============================================
# TOOL 4: Search Repositories
# ============================================

def search_repos(query: str, max_results: int = 10) -> dict:
    """Search GitHub repositories."""
    logger.info("searching_repos", query=query)
    
    try:
        result = _github_request(
            "/search/repositories",
            params={
                "q": query,
                "per_page": max_results,
                "sort": "stars",
                "order": "desc",
            }
        )
        
        simplified = [
            {
                "name": repo["name"],
                "full_name": repo["full_name"],
                "description": repo.get("description") or "No description",
                "language": repo.get("language") or "Unknown",
                "stars": repo["stargazers_count"],
                "url": repo["html_url"],
            }
            for repo in result.get("items", [])
        ]
        
        return {
            "query": query,
            "total_count": result.get("total_count", 0),
            "shown": len(simplified),
            "results": simplified,
        }
    
    except GitHubAPIError as e:
        return {"error": "github_api_error", "message": str(e)}
    except GitHubTransientError as e:
        return {"error": "temporary_error", "message": str(e)}


search_repos_schema = {
    "type": "function",
    "function": {
        "name": "search_repos",
        "description": "Search GitHub repositories by keyword. Returns top repositories sorted by stars.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'machine learning python', 'react components')"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results (default 10)",
                    "minimum": 1,
                    "maximum": 100,
                }
            },
            "required": ["query"]
        }
    }
}

# ============================================
# TOOL 5: Get My Profile (Authenticated User)
# ============================================

def get_my_profile() -> dict:
    """Get authenticated user's profile."""
    logger.info("getting_my_profile")
    
    try:
        user = _github_request("/user")
        return {
            "username": user["login"],
            "name": user.get("name"),
            "email": user.get("email"),
            "bio": user.get("bio"),
            "public_repos": user["public_repos"],
            "followers": user["followers"],
            "following": user["following"],
            "created_at": user["created_at"],
            "url": user["html_url"],
        }
    except GitHubAPIError as e:
        return {"error": "github_api_error", "message": str(e)}
    except GitHubTransientError as e:
        return {"error": "temporary_error", "message": str(e)}


my_profile_schema = {
    "type": "function",
    "function": {
        "name": "get_my_profile",
        "description": (
            "Get the authenticated user's GitHub profile information. "
            "Use this when user asks about 'my' profile, 'my' account, 'my' GitHub, etc."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []}
    }
}


# ============================================
# TOOL 6: Get My Repositories
# ============================================

def get_my_repos(max_results: int = 30) -> dict:
    """Get repositories for the authenticated user."""
    logger.info("getting_my_repos", max_results=max_results)
    
    try:
        repos = _github_request(
            "/user/repos",
            params={
                "per_page": max_results,
                "sort": "updated",
                "affiliation": "owner",
            }
        )
        
        simplified = [
            {
                "name": repo["name"],
                "description": repo.get("description") or "No description",
                "language": repo.get("language") or "Unknown",
                "private": repo["private"],
                "stars": repo["stargazers_count"],
                "forks": repo["forks_count"],
                "open_issues": repo["open_issues_count"],
                "updated_at": repo["updated_at"],
                "url": repo["html_url"],
            }
            for repo in repos
        ]
        
        return {
            "total_shown": len(simplified),
            "repos": simplified,
        }
    except GitHubAPIError as e:
        return {"error": "github_api_error", "message": str(e)}
    except GitHubTransientError as e:
        return {"error": "temporary_error", "message": str(e)}


my_repos_schema = {
    "type": "function",
    "function": {
        "name": "get_my_repos",
        "description": (
            "Get authenticated user's own repositories (includes private repos). "
            "Use this when user asks about 'my repos', 'my projects', 'my repositories', etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of repos to return (default 30)",
                    "minimum": 1,
                    "maximum": 100,
                }
            },
            "required": []
        }
    }
}


# ============================================
# TOOL 7: Get Repository README
# ============================================

def get_repo_readme(owner: str, repo: str) -> dict:
    """Get the README content of a repository."""
    logger.info("getting_readme", owner=owner, repo=repo)
    
    try:
        readme = _github_request(f"/repos/{owner}/{repo}/readme")
        
        import base64
        content = base64.b64decode(readme["content"]).decode("utf-8")
        
        # Truncate if too long
        if len(content) > 3000:
            content = content[:3000] + "\n... (truncated)"
        
        return {
            "repo": f"{owner}/{repo}",
            "filename": readme["name"],
            "size": readme["size"],
            "content": content,
        }
    except GitHubAPIError as e:
        return {"error": "github_api_error", "message": str(e)}
    except GitHubTransientError as e:
        return {"error": "temporary_error", "message": str(e)}


get_readme_schema = {
    "type": "function",
    "function": {
        "name": "get_repo_readme",
        "description": (
            "Get README content of a GitHub repository. "
            "Useful for understanding what a project is about, its usage, features, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {
                    "type": "string",
                    "description": "Repository owner username"
                },
                "repo": {
                    "type": "string",
                    "description": "Repository name"
                },
            },
            "required": ["owner", "repo"]
        }
    }
}

# ============================================
# Registration Helper
# ============================================

ALL_GITHUB_TOOLS = [
    (list_repos_schema, list_user_repos),
    (get_issues_schema, get_repo_issues),
    (get_repo_schema, get_repo_details),
    (search_repos_schema, search_repos),
    (my_profile_schema, get_my_profile),
    (my_repos_schema, get_my_repos),
    (get_readme_schema, get_repo_readme),
]

def register_github_tools(agent):
    """Register all GitHub tools with an agent."""
    for schema, function in ALL_GITHUB_TOOLS:
        agent.register_tool(schema, function)