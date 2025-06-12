"""
OpenAPI specification handling for the doc-monitor MCP server.
Handles fetching, parsing, and processing OpenAPI specifications.
"""
import json
from typing import Optional, List, Dict, Any
import requests
import yaml


def fetch_openapi_spec(url: str) -> Optional[Dict[str, Any]]:
    """
    Fetch and parse an OpenAPI spec from a URL (json or yaml).
    
    Args:
        url: URL of the OpenAPI specification
        
    Returns:
        The parsed spec dict, or None if not valid OpenAPI
    """
    try:
        resp = requests.get(url)
        if resp.status_code != 200:
            print(f"Failed to fetch OpenAPI spec {url}: HTTP {resp.status_code}")
            return None
        
        content_type = resp.headers.get('Content-Type', '').lower()
        text = resp.text
        
        # Try parsing as JSON first
        try:
            spec = json.loads(text)
        except json.JSONDecodeError:
            # Try parsing as YAML
            try:
                spec = yaml.safe_load(text)
            except yaml.YAMLError:
                print(f"Failed to parse OpenAPI spec {url}: Invalid JSON/YAML format")
                return None
        
        # Validate that it's an OpenAPI/Swagger spec
        if not (isinstance(spec, dict) and ('openapi' in spec or 'swagger' in spec)):
            print(f"Invalid OpenAPI spec {url}: Missing openapi/swagger field")
            return None
        
        print(f"[INFO] Successfully fetched OpenAPI spec from {url}")
        return spec
        
    except Exception as e:
        print(f"Error fetching OpenAPI spec {url}: {e}")
        return None


def openapi_spec_to_markdown_chunks(spec: Dict[str, Any], chunk_size: int = 5000) -> List[Dict[str, Any]]:
    """
    Convert an OpenAPI spec dict to a list of markdown chunks with metadata.
    
    Args:
        spec: The OpenAPI specification dictionary
        chunk_size: Maximum size for each chunk
        
    Returns:
        List of dictionaries with 'content' and 'metadata' keys
    """
    chunks = []
    
    # 1. Process info section
    info = spec.get('info', {})
    title = info.get('title', 'OpenAPI Spec')
    version = info.get('version', '')
    description = info.get('description', '')
    
    header = f"# {title}\n\nVersion: {version}\n\n{description}\n"
    chunks.append({
        'content': header.strip(),
        'metadata': {
            'type': 'openapi',
            'section': 'info',
            'title': title,
            'version': version
        }
    })
    
    # 2. Process paths (endpoints)
    paths = spec.get('paths', {})
    for path, methods in paths.items():
        for method, details in methods.items():
            if not isinstance(details, dict):
                continue
            
            endpoint_content = _format_endpoint_markdown(method, path, details)
            chunks.append({
                'content': endpoint_content,
                'metadata': {
                    'type': 'openapi',
                    'section': 'endpoint',
                    'path': path,
                    'method': method.upper(),
                    'summary': details.get('summary', '')
                }
            })
    
    # 3. Process components/schemas
    components = spec.get('components', {}).get('schemas', {})
    for name, schema in components.items():
        schema_content = f"### Schema: `{name}`\n\n```json\n{json.dumps(schema, indent=2)}\n```\n"
        chunks.append({
            'content': schema_content.strip(),
            'metadata': {
                'type': 'openapi',
                'section': 'schema',
                'name': name
            }
        })
    
    # 4. Split large chunks if necessary
    final_chunks = []
    for chunk in chunks:
        content = chunk['content']
        if len(content) > chunk_size:
            # Split large chunks
            parts = _split_content(content, chunk_size)
            for i, part in enumerate(parts):
                meta = dict(chunk['metadata'])
                meta['part'] = i
                final_chunks.append({'content': part, 'metadata': meta})
        else:
            final_chunks.append(chunk)
    
    print(f"[INFO] Generated {len(final_chunks)} chunks from OpenAPI spec")
    return final_chunks


def _format_endpoint_markdown(method: str, path: str, details: Dict[str, Any]) -> str:
    """Format an API endpoint as markdown."""
    summary = details.get('summary', '')
    description = details.get('description', '')
    parameters = details.get('parameters', [])
    responses = details.get('responses', {})
    
    md = f"## `{method.upper()} {path}`\n\n"
    
    if summary:
        md += f"**Summary:** {summary}\n\n"
    
    if description:
        md += f"**Description:** {description}\n\n"
    
    # Parameters
    if parameters:
        md += "**Parameters:**\n"
        for param in parameters:
            param_name = param.get('name', '')
            param_desc = param.get('description', '')
            param_required = param.get('required', False)
            param_location = param.get('in', '')
            
            md += f"- `{param_name}` ({param_location}, {'required' if param_required else 'optional'}): {param_desc}\n"
        md += "\n"
    
    # Request body
    request_body = details.get('requestBody', {})
    if request_body:
        md += "**Request Body:**\n"
        content = request_body.get('content', {})
        for content_type, schema_info in content.items():
            md += f"- Content-Type: `{content_type}`\n"
            schema = schema_info.get('schema', {})
            if schema:
                md += f"  - Schema: `{schema.get('type', 'object')}`\n"
        md += "\n"
    
    # Responses
    if responses:
        md += "**Responses:**\n"
        for code, response in responses.items():
            response_desc = response.get('description', '') if isinstance(response, dict) else str(response)
            md += f"- `{code}`: {response_desc}\n"
        md += "\n"
    
    return md.strip()


def _split_content(content: str, chunk_size: int) -> List[str]:
    """Split content into smaller chunks."""
    parts = []
    start = 0
    
    while start < len(content):
        end = start + chunk_size
        if end >= len(content):
            parts.append(content[start:].strip())
            break
        
        # Try to find a good split point
        chunk = content[start:end]
        
        # Look for paragraph breaks
        last_para = chunk.rfind('\n\n')
        if last_para > chunk_size * 0.5:
            end = start + last_para
        elif '\n' in chunk:
            last_line = chunk.rfind('\n')
            if last_line > chunk_size * 0.5:
                end = start + last_line
        
        parts.append(content[start:end].strip())
        start = end
    
    return [part for part in parts if part]


def extract_openapi_info(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract key information from an OpenAPI specification.
    
    Args:
        spec: OpenAPI specification dictionary
        
    Returns:
        Dictionary with extracted information
    """
    info = spec.get('info', {})
    paths = spec.get('paths', {})
    components = spec.get('components', {})
    
    endpoint_count = sum(len([m for m in methods if isinstance(methods.get(m), dict)]) 
                        for methods in paths.values())
    
    schema_count = len(components.get('schemas', {}))
    
    return {
        'title': info.get('title', 'Unknown'),
        'version': info.get('version', 'Unknown'),
        'description': info.get('description', ''),
        'endpoint_count': endpoint_count,
        'schema_count': schema_count,
        'servers': spec.get('servers', []),
        'openapi_version': spec.get('openapi') or spec.get('swagger', 'Unknown')
    } 