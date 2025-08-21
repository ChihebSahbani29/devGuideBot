# GitHub Agent - API Usage Guide

This guide explains how to use the GitHub Agent's various actions with clear examples.

## Table of Contents
- [Available Actions](#available-actions)
- [Common Parameters](#common-parameters)
- [Action Details](#action-details)
  - [ingest_data](#ingest_data)
  - [get_file](#get_file)
  - [list_repositories](#list_repositories)
  - [search_code](#search_code)

## Available Actions

1. `ingest_data` - Fetch and process all files from a repository
2. `get_file` - Get the content of a specific file
3. `list_repositories` - List repositories for a user/organization
4. `search_code` - Search code across repositories

## Common Parameters

- `owner`: (string) GitHub username or organization name
- `repo`: (string) Repository name
- `ref`: (string, optional) Branch/tag name (default: 'main')

## Action Details

### ingest_data
Fetches and processes all files from the specified repository.

**Example Request:**
```json
{
  "action": "ingest_data",
  "parameters": {
    "owner": "github",
    "repo": "docs"
  }
}
```

**Response:**
```json
{
  "success": true,
  "result": {
    "documents_ingested": 42,
    "repository": "github/docs"
  },
  "execution_time": 3.45
}
```

### get_file
Gets the content of a specific file from a repository.

**Example Request:**
```json
{
  "action": "get_file",
  "parameters": {
    "owner": "github",
    "repo": "docs",
    "path": "README.md",
    "ref": "main"
  }
}
```

**Response:**
```json
{
  "success": true,
  "result": {
    "content": "# GitHub Documentation\n\nWelcome to the GitHub documentation...",
    "path": "README.md",
    "sha": "abc123...",
    "html_url": "https://github.com/github/docs/blob/main/README.md"
  },
  "execution_time": 0.23
}
```

### list_repositories
Lists repositories for a user or organization.

**Example Request:**
```json
{
  "action": "list_repositories",
  "parameters": {
    "owner": "github"
  }
}
```

**Response:**
```json
{
  "success": true,
  "result": {
    "repositories": [
      {
        "name": "docs",
        "full_name": "github/docs",
        "description": "The open-source repo for docs.github.com",
        "html_url": "https://github.com/github/docs",
        "private": false
      },
      ...
    ],
    "total_count": 42
  },
  "execution_time": 0.56
}
```

### search_code
Searches code across repositories.

**Example Request:**
```json
{
  "action": "search_code",
  "parameters": {
    "query": "class GitHubAgent",
    "owner": "github",
    "repo": "docs"
  }
}
```

**Response:**
```json
{
  "success": true,
  "result": {
    "total_count": 5,
    "items": [
      {
        "name": "github_agent.py",
        "path": "src/agents/github_agent.py",
        "html_url": "https://github.com/github/docs/blob/main/src/agents/github_agent.py",
        "repository": {
          "full_name": "github/docs"
        }
      }
    ]
  },
  "execution_time": 0.78
}
```

## Error Handling

All endpoints return errors in a consistent format:

```json
{
  "success": false,
  "error": "Error message describing what went wrong",
  "execution_time": 0.12
}
```

Common error cases:
- Missing required parameters
- Invalid repository or file path
- Authentication errors
- Rate limiting

## Best Practices

1. Always check the `success` field before processing results
2. Handle rate limiting (check `X-RateLimit-*` headers)
3. Use the `ref` parameter to specify a specific branch/tag
4. For large repositories, consider using pagination where available
