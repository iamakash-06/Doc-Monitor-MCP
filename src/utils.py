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

def improved_semantic_search(
    client: Client,
    query: str,
    match_count: int = 10,
    filter_metadata: Optional[Dict[str, Any]] = None,
    similarity_threshold: float = 0.3,
    enable_reranking: bool = True
) -> List[Dict[str, Any]]:
    """
    Improved semantic search with query preprocessing, hybrid search, and reranking.
    
    Args:
        client: Supabase client
        query: Search query
        match_count: Number of results to return
        filter_metadata: Metadata filters
        similarity_threshold: Minimum similarity score (0-1)
        enable_reranking: Whether to enable reranking
    
    Returns:
        List of improved search results
    """
    try:
        # 1. Preprocess query for better embedding
        processed_query = _preprocess_query(query)
        
        # 2. Get initial vector search results (get more for reranking)
        initial_count = match_count * 3 if enable_reranking else match_count
        vector_results = _enhanced_vector_search(
            client, processed_query, initial_count, filter_metadata, similarity_threshold
        )
        
        if not vector_results:
            return []
        
        # 3. Optional: Add keyword/BM25-style search for hybrid approach
        keyword_results = _keyword_search(client, query, filter_metadata)
        
        # 4. Combine and deduplicate results
        combined_results = _combine_search_results(vector_results, keyword_results)
        
        # 5. Rerank results if enabled
        if enable_reranking and len(combined_results) > match_count:
            final_results = _rerank_results(query, combined_results, match_count)
        else:
            final_results = combined_results[:match_count]
        
        return final_results
        
    except Exception as e:
        print(f"Error in improved semantic search: {e}")
        # Fallback to original search
        return semantic_search_documents(client, query, match_count, filter_metadata)

def _preprocess_query(query: str) -> str:
    """Preprocess query for better embedding quality."""
    import re
    
    # Remove excessive whitespace
    query = re.sub(r'\s+', ' ', query.strip())
    
    # Expand common abbreviations and technical terms
    expansions = {
        'api': 'API application programming interface',
        'auth': 'authentication authorization',
        'db': 'database',
        'ui': 'user interface',
        'ux': 'user experience',
        'ssl': 'SSL secure socket layer',
        'http': 'HTTP hypertext transfer protocol',
        'json': 'JSON javascript object notation',
        'xml': 'XML extensible markup language'
    }
    
    query_lower = query.lower()
    for abbrev, expansion in expansions.items():
        if abbrev in query_lower:
            query = f"{query} {expansion}"
    
    return query

def _enhanced_vector_search(
    client: Client,
    query: str, 
    match_count: int,
    filter_metadata: Optional[Dict[str, Any]],
    similarity_threshold: float
) -> List[Dict[str, Any]]:
    """Enhanced vector search with similarity threshold."""
    query_embedding = create_single_embedding(query)
    
    try:
        params = {
            'query_embedding': query_embedding,
            'match_count': match_count,
            'similarity_threshold': similarity_threshold
        }
        if filter_metadata:
            params['filter'] = filter_metadata
            
        result = client.rpc('enhanced_match_crawled_pages', params).execute()
        return result.data or []
    except Exception as e:
        print(f"Enhanced search failed, falling back to basic search: {e}")
        # Fallback to original function
        return semantic_search_documents(client, query, match_count, filter_metadata)

def _keyword_search(
    client: Client,
    query: str,
    filter_metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Perform keyword-based search for hybrid results."""
    try:
        # Simple keyword search using basic text matching
        # We'll use a simple ILIKE search instead of full-text search for compatibility
        search_terms = query.lower().split()
        
        if not search_terms:
            return []
        
        # Build a basic query
        base_query = client.table("crawled_pages").select(
            "id, url, chunk_number, content, metadata, version"
        )
        
        # For keyword search, we'll use simple ILIKE pattern matching
        # This is more compatible with the Supabase client
        search_pattern = f"%{' '.join(search_terms)}%"
        base_query = base_query.ilike("content", search_pattern)
        
        # Apply metadata filter if provided
        if filter_metadata:
            for key, value in filter_metadata.items():
                base_query = base_query.eq(f"metadata->>{key}", value)
        
        # Execute the query
        result = base_query.execute()
        
        # Add similarity score to results (fixed score of 0.5 for keyword matches)
        results = result.data or []
        for item in results:
            item['similarity'] = 0.5
        
        return results[:10]  # Limit to 10 results
        
    except Exception as e:
        print(f"Keyword search failed: {e}")
        return []

def _combine_search_results(
    vector_results: List[Dict[str, Any]], 
    keyword_results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Combine and deduplicate search results."""
    seen_chunks = set()
    combined = []
    
    # Add vector results first (higher priority)
    for result in vector_results:
        chunk_id = (result.get('url'), result.get('chunk_number'))
        if chunk_id not in seen_chunks:
            seen_chunks.add(chunk_id)
            combined.append(result)
    
    # Add keyword results that weren't already included
    for result in keyword_results:
        chunk_id = (result.get('url'), result.get('chunk_number'))
        if chunk_id not in seen_chunks:
            seen_chunks.add(chunk_id)
            combined.append(result)
    
    return combined

def _rerank_results(query: str, results: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    """Rerank results using cross-encoder or heuristic scoring."""
    try:
        # Simple heuristic reranking (you could use a cross-encoder model here)
        query_terms = set(query.lower().split())
        
        for result in results:
            content = result.get('content', '').lower()
            metadata = result.get('metadata', {})
            
            # Base score from similarity
            base_score = float(result.get('similarity', 0))
            
            # Boost for exact query term matches
            exact_matches = sum(1 for term in query_terms if term in content)
            exact_match_boost = exact_matches * 0.1
            
            # Boost for title/header matches
            headers = metadata.get('headers', '')
            header_boost = 0.15 if any(term in headers.lower() for term in query_terms) else 0
            
            # Boost for metadata relevance
            section_boost = 0.1 if metadata.get('section') in ['info', 'endpoint'] else 0
            
            # Calculate final score
            final_score = base_score + exact_match_boost + header_boost + section_boost
            result['rerank_score'] = final_score
        
        # Sort by rerank score and return top_k
        reranked = sorted(results, key=lambda x: x.get('rerank_score', 0), reverse=True)
        return reranked[:top_k]
        
    except Exception as e:
        print(f"Reranking failed: {e}")
        # Fallback to original order
        return results[:top_k]

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

def semantic_chunk_markdown(text: str, target_chunk_size: int = 1500, overlap_size: int = 200) -> List[str]:
    """
    Improved chunking that creates semantic chunks with overlaps for better retrieval.
    
    Args:
        text: The markdown text to chunk
        target_chunk_size: Target size for each chunk (smaller for better semantic coherence)
        overlap_size: Overlap between chunks to maintain context
    
    Returns:
        List of text chunks with semantic boundaries and overlaps
    """
    import re
    
    # First, split by major sections (headers)
    sections = re.split(r'\n(?=#+\s)', text)
    
    chunks = []
    current_chunk = ""
    
    for section in sections:
        section = section.strip()
        if not section:
            continue
            
        # If section alone is larger than target, split it further
        if len(section) > target_chunk_size:
            # If we have a current chunk, add it first
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            # Split large section into smaller parts
            section_chunks = _split_large_section(section, target_chunk_size, overlap_size)
            chunks.extend(section_chunks)
        else:
            # Check if adding this section would exceed target size
            if len(current_chunk) + len(section) > target_chunk_size and current_chunk:
                # Add current chunk and start new one with overlap
                chunks.append(current_chunk.strip())
                
                # Create overlap from end of previous chunk
                overlap = _get_overlap_text(current_chunk, overlap_size)
                current_chunk = overlap + "\n\n" + section if overlap else section
            else:
                # Add section to current chunk
                current_chunk = current_chunk + "\n\n" + section if current_chunk else section
    
    # Add final chunk if exists
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    # Filter out very small chunks (less than 100 characters)
    return [chunk for chunk in chunks if len(chunk) >= 100]

def _split_large_section(text: str, target_size: int, overlap_size: int) -> List[str]:
    """Split a large section into smaller chunks with overlaps."""
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + target_size
        
        if end >= len(text):
            chunks.append(text[start:].strip())
            break
        
        # Find best split point
        chunk_text = text[start:end]
        
        # Try to split at paragraph breaks first
        last_para = chunk_text.rfind('\n\n')
        if last_para > target_size * 0.6:
            end = start + last_para
        else:
            # Try sentence boundaries
            last_sentence = chunk_text.rfind('. ')
            if last_sentence > target_size * 0.6:
                end = start + last_sentence + 1
            else:
                # Try line breaks
                last_line = chunk_text.rfind('\n')
                if last_line > target_size * 0.6:
                    end = start + last_line
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start back by overlap_size to create overlap
        start = max(start + len(chunk) - overlap_size, end - overlap_size)
        if start >= end:
            start = end
    
    return chunks

def _get_overlap_text(text: str, overlap_size: int) -> str:
    """Get overlap text from the end of a chunk."""
    if len(text) <= overlap_size:
        return text
    
    # Try to get overlap at sentence boundary
    overlap_start = len(text) - overlap_size
    overlap_text = text[overlap_start:]
    
    # Find first sentence start in overlap
    first_sentence = overlap_text.find('. ')
    if first_sentence != -1 and first_sentence < overlap_size * 0.5:
        return overlap_text[first_sentence + 2:]
    
    return overlap_text

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