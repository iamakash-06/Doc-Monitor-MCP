"""
Search and RAG functionality for the doc-monitor MCP server.
Handles semantic search, vector search, and query processing.
"""
import re
from typing import List, Dict, Any, Optional
from supabase import Client
from .embeddings import create_single_embedding


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
        return result.data or []
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
        search_terms = query.lower().split()
        
        if not search_terms:
            return []
        
        # Build a basic query
        base_query = client.table("crawled_pages").select(
            "id, url, chunk_number, content, metadata, version"
        )
        
        # For keyword search, we'll use simple ILIKE pattern matching
        search_pattern = f"%{' '.join(search_terms)}%"
        base_query = base_query.ilike("content", search_pattern)
        
        # Apply metadata filter if provided
        if filter_metadata:
            for key, value in filter_metadata.items():
                base_query = base_query.eq(f"metadata->>{key}", value)
        
        # Execute the query
        result = base_query.execute()
        
        # Add similarity score to results (fixed score for keyword matches)
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