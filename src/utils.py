"""
Utility functions for the doc-monitor MCP server.
"""
import os
import concurrent.futures
from typing import List, Dict, Any, Optional, Tuple
import json
from supabase import create_client, Client
from urllib.parse import urlparse
import openai
import yaml
import requests

# --- Supabase Client & Embedding Utilities ---

def get_supabase_client() -> Client:
    """
    Create and return a Supabase client using environment variables.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment variables")
    return create_client(url, key)

def batch_create_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Create embeddings for a list of texts using OpenAI's API.
    Returns a list of embeddings (each embedding is a list of floats).
    """
    if not texts:
        return []
    try:
        response = openai.embeddings.create(
            model="text-embedding-3-small",
            input=texts
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"Error creating batch embeddings: {e}")
        return [[0.0] * 1536 for _ in range(len(texts))]

def create_single_embedding(text: str) -> List[float]:
    """
    Create an embedding for a single text using OpenAI's API.
    Returns a list of floats representing the embedding.
    """
    try:
        embeddings = batch_create_embeddings([text])
        return embeddings[0] if embeddings else [0.0] * 1536
    except Exception as e:
        print(f"Error creating embedding: {e}")
        return [0.0] * 1536

# --- Contextual Embedding Utilities ---

def contextualize_chunk(full_document: str, chunk: str) -> Tuple[str, bool]:
    """
    Generate contextual information for a chunk within a document to improve retrieval.
    Returns (contextual_text, was_contextualized).
    """
    model_choice = os.getenv("MODEL_CHOICE")
    try:
        prompt = f"""<document> 
{full_document[:25000]} 
</document>
Here is the chunk we want to situate within the whole document 
<chunk> 
{chunk}
</chunk> 
Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""
        response = openai.chat.completions.create(
            model=model_choice,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides concise contextual information."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        context = response.choices[0].message.content.strip()
        contextual_text = f"{context}\n---\n{chunk}"
        return contextual_text, True
    except Exception as e:
        print(f"Error generating contextual embedding: {e}. Using original chunk instead.")
        return chunk, False

def contextualize_chunk_worker(args):
    """
    Worker for contextualizing a chunk (for use with concurrent.futures).
    Args: (url, content, full_document)
    Returns: (contextual_text, was_contextualized)
    """
    url, content, full_document = args
    return contextualize_chunk(full_document, content)

# --- Supabase Document Operations ---

def batch_upsert_documents(
    client: Client, 
    urls: List[str], 
    chunk_numbers: List[int],
    contents: List[str], 
    metadatas: List[Dict[str, Any]],
    url_to_full_document: Dict[str, str],
    batch_size: int = 20
) -> None:
    """
    Add or update documents in the Supabase crawled_pages table in batches.
    Deletes existing records with the same URLs before inserting to prevent duplicates.
    """
    unique_urls = list(set(urls))
    try:
        if unique_urls:
            client.table("crawled_pages").delete().in_("url", unique_urls).execute()
    except Exception as e:
        print(f"Batch delete failed: {e}. Trying one-by-one deletion as fallback.")
        for url in unique_urls:
            try:
                client.table("crawled_pages").delete().eq("url", url).execute()
            except Exception as inner_e:
                print(f"Error deleting record for URL {url}: {inner_e}")
    model_choice = os.getenv("MODEL_CHOICE")
    use_contextual = bool(model_choice)
    for i in range(0, len(contents), batch_size):
        batch_end = min(i + batch_size, len(contents))
        batch_urls = urls[i:batch_end]
        batch_chunk_numbers = chunk_numbers[i:batch_end]
        batch_contents = contents[i:batch_end]
        batch_metadatas = metadatas[i:batch_end]
        if use_contextual:
            process_args = []
            for j, content in enumerate(batch_contents):
                url = batch_urls[j]
                full_document = url_to_full_document.get(url, "")
                process_args.append((url, content, full_document))
            contextual_contents = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_idx = {executor.submit(contextualize_chunk_worker, arg): idx 
                                for idx, arg in enumerate(process_args)}
                for future in concurrent.futures.as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        result, success = future.result()
                        contextual_contents.append(result)
                        if success:
                            batch_metadatas[idx]["contextual_embedding"] = True
                    except Exception as e:
                        print(f"Error processing chunk {idx}: {e}")
                        contextual_contents.append(batch_contents[idx])
            if len(contextual_contents) != len(batch_contents):
                print(f"Warning: Expected {len(batch_contents)} results but got {len(contextual_contents)}")
                contextual_contents = batch_contents
        else:
            contextual_contents = batch_contents
        batch_embeddings = batch_create_embeddings(contextual_contents)
        batch_data = []
        for j in range(len(contextual_contents)):
            chunk_size = len(contextual_contents[j])
            data = {
                "url": batch_urls[j],
                "chunk_number": batch_chunk_numbers[j],
                "content": contextual_contents[j],
                "metadata": {
                    "chunk_size": chunk_size,
                    **batch_metadatas[j]
                },
                "embedding": batch_embeddings[j]
            }
            batch_data.append(data)
        try:
            client.table("crawled_pages").insert(batch_data).execute()
        except Exception as e:
            print(f"Error inserting batch into Supabase: {e}")

def semantic_search_documents(
    client: Client, 
    query: str, 
    match_count: int = 10, 
    filter_metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Search for documents in Supabase using vector similarity.
    Returns a list of matching documents.
    """
    query_embedding = create_single_embedding(query)
    try:
        params = {
            'query_embedding': query_embedding,
            'match_count': match_count
        }
        if filter_metadata:
            params['filter'] = filter_metadata
        result = client.rpc('match_crawled_pages', params).execute()
        return result.data
    except Exception as e:
        print(f"Error searching documents: {e}")
        return []

# --- OpenAPI Utilities ---

def is_openapi_url(url: str) -> bool:
    """
    Return True if the URL is likely an OpenAPI spec (json/yaml).
    """
    lowered = url.lower()
    return lowered.endswith('.json') or lowered.endswith('.yaml') or lowered.endswith('.yml')

def fetch_openapi_spec(url: str) -> Optional[dict]:
    """
    Fetch and parse an OpenAPI spec from a URL (json or yaml).
    Returns the parsed spec dict, or None if not valid OpenAPI.
    """
    try:
        resp = requests.get(url)
        if resp.status_code != 200:
            return None
        content_type = resp.headers.get('Content-Type', '').lower()
        text = resp.text
        try:
            spec = json.loads(text)
        except Exception:
            try:
                spec = yaml.safe_load(text)
            except Exception:
                return None
        if not (isinstance(spec, dict) and ('openapi' in spec or 'swagger' in spec)):
            return None
        return spec
    except Exception:
        return None

def openapi_spec_to_markdown_chunks(spec: dict, chunk_size: int = 5000) -> List[dict]:
    """
    Convert an OpenAPI spec dict to a list of markdown chunks with metadata.
    Each chunk is a dict with 'content' and 'metadata'.
    """
    chunks = []
    info = spec.get('info', {})
    title = info.get('title', 'OpenAPI Spec')
    version = info.get('version', '')
    description = info.get('description', '')
    header = f"# {title}\n\nVersion: {version}\n\n{description}\n"
    chunks.append({
        'content': header.strip(),
        'metadata': {'type': 'openapi', 'section': 'info', 'title': title, 'version': version}
    })
    paths = spec.get('paths', {})
    for path, methods in paths.items():
        for method, details in methods.items():
            if not isinstance(details, dict):
                continue
            summary = details.get('summary', '')
            desc = details.get('description', '')
            params = details.get('parameters', [])
            responses = details.get('responses', {})
            md = f"## `{method.upper()} {path}`\n\n"
            if summary:
                md += f"**Summary:** {summary}\n\n"
            if desc:
                md += f"**Description:** {desc}\n\n"
            if params:
                md += "**Parameters:**\n"
                for p in params:
                    pname = p.get('name', '')
                    pdesc = p.get('description', '')
                    preq = p.get('required', False)
                    md += f"- `{pname}` ({'required' if preq else 'optional'}): {pdesc}\n"
                md += "\n"
            if responses:
                md += "**Responses:**\n"
                for code, resp in responses.items():
                    rdesc = resp.get('description', '') if isinstance(resp, dict) else str(resp)
                    md += f"- `{code}`: {rdesc}\n"
            chunks.append({
                'content': md.strip(),
                'metadata': {
                    'type': 'openapi',
                    'section': 'endpoint',
                    'path': path,
                    'method': method.upper(),
                    'summary': summary
                }
            })
    components = spec.get('components', {}).get('schemas', {})
    for name, schema in components.items():
        md = f"### Schema: `{name}`\n\n{json.dumps(schema, indent=2)}\n"
        chunks.append({
            'content': md.strip(),
            'metadata': {'type': 'openapi', 'section': 'schema', 'name': name}
        })
    final_chunks = []
    for c in chunks:
        content = c['content']
        if len(content) > chunk_size:
            for i in range(0, len(content), chunk_size):
                part = content[i:i+chunk_size]
                meta = dict(c['metadata'])
                meta['part'] = i // chunk_size
                final_chunks.append({'content': part, 'metadata': meta})
        else:
            final_chunks.append(c)
    return final_chunks

def is_sitemap(url: str) -> bool:
    """Return True if the URL is a sitemap."""
    return url.endswith('sitemap.xml') or 'sitemap' in urlparse(url).path

def is_txt(url: str) -> bool:
    """Return True if the URL is a text file."""
    return url.endswith('.txt')

def parse_sitemap(sitemap_url: str) -> List[str]:
    """Parse a sitemap and extract URLs as a list of strings."""
    resp = requests.get(sitemap_url)
    if resp.status_code != 200:
        return []
    try:
        from xml.etree import ElementTree
        tree = ElementTree.fromstring(resp.content)
        return [loc.text for loc in tree.findall('.//{*}loc')]
    except Exception as e:
        print(f"Error parsing sitemap XML: {e}")
        return []

def smart_chunk_markdown(text: str, chunk_size: int = 5000) -> List[str]:
    """Split text into chunks, respecting code blocks and paragraphs."""
    chunks = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = start + chunk_size
        if end >= text_length:
            chunks.append(text[start:].strip())
            break
        chunk = text[start:end]
        code_block = chunk.rfind('```')
        if code_block != -1 and code_block > chunk_size * 0.3:
            end = start + code_block
        elif '\n\n' in chunk:
            last_break = chunk.rfind('\n\n')
            if last_break > chunk_size * 0.3:
                end = start + last_break
        elif '. ' in chunk:
            last_period = chunk.rfind('. ')
            if last_period > chunk_size * 0.3:
                end = start + last_period + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks

def extract_section_info(chunk: str) -> Dict[str, Any]:
    """Extract headers and stats from a markdown chunk."""
    import re
    headers = re.findall(r'^(#+)\s+(.+)$', chunk, re.MULTILINE)
    header_str = '; '.join(f'{h[0]} {h[1]}' for h in headers) if headers else ''
    return {
        "headers": header_str,
        "char_count": len(chunk),
        "word_count": len(chunk.split())
    }