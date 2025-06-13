"""
Database operations for the doc-monitor MCP server.
Handles Supabase client creation and document storage operations.
"""
import os
from typing import List, Dict, Any
import concurrent.futures
from supabase import create_client, Client

from embeddings import batch_create_embeddings, contextualize_chunk_worker

def get_supabase_client() -> Client:
    """
    Create and return a Supabase client using environment variables.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment variables")
    return create_client(url, key)


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
    
    # Delete existing records to prevent duplicates
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
    
    # Check if contextual embeddings are enabled
    model_choice = os.getenv("MODEL_CHOICE")
    use_contextual = bool(model_choice)
    
    # Process documents in batches
    for i in range(0, len(contents), batch_size):
        batch_end = min(i + batch_size, len(contents))
        batch_urls = urls[i:batch_end]
        batch_chunk_numbers = chunk_numbers[i:batch_end]
        batch_contents = contents[i:batch_end]
        batch_metadatas = metadatas[i:batch_end]
        
        # Apply contextual processing if enabled
        if use_contextual:
            contextual_contents = _process_contextual_batch(
                batch_urls, batch_contents, batch_metadatas, url_to_full_document
            )
        else:
            contextual_contents = batch_contents
        
        # Create embeddings and batch data
        batch_embeddings = batch_create_embeddings(contextual_contents)
        batch_data = _build_batch_data(
            batch_urls, batch_chunk_numbers, contextual_contents, 
            batch_metadatas, batch_embeddings
        )
        
        # Insert batch into database
        try:
            client.table("crawled_pages").insert(batch_data).execute()
        except Exception as e:
            print(f"Error inserting batch into Supabase: {e}")


def _process_contextual_batch(
    batch_urls: List[str], 
    batch_contents: List[str], 
    batch_metadatas: List[Dict[str, Any]], 
    url_to_full_document: Dict[str, str]
) -> List[str]:
    """Process batch contents with contextual embeddings."""
    process_args = []
    for j, content in enumerate(batch_contents):
        url = batch_urls[j]
        full_document = url_to_full_document.get(url, "")
        process_args.append((url, content, full_document))
    
    contextual_contents = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_idx = {
            executor.submit(contextualize_chunk_worker, arg): idx 
            for idx, arg in enumerate(process_args)
        }
        
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
    
    return contextual_contents


def _build_batch_data(
    batch_urls: List[str], 
    batch_chunk_numbers: List[int], 
    contextual_contents: List[str], 
    batch_metadatas: List[Dict[str, Any]], 
    batch_embeddings: List[List[float]]
) -> List[Dict[str, Any]]:
    """Build batch data for database insertion."""
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
    return batch_data 