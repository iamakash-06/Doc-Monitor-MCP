"""
AI Embeddings and contextual processing for the doc-monitor MCP server.
Handles OpenAI embeddings creation and contextual chunk processing.
"""
import os
from typing import List, Tuple
import openai


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
        # Return default embeddings on error
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


def contextualize_chunk(full_document: str, chunk: str) -> Tuple[str, bool]:
    """
    Generate contextual information for a chunk within a document to improve retrieval.
    Returns (contextual_text, was_contextualized).
    """
    model_choice = os.getenv("MODEL_CHOICE")
    if not model_choice:
        return chunk, False
    
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


def contextualize_chunk_worker(args) -> Tuple[str, bool]:
    """
    Worker function for contextualizing a chunk (for use with concurrent.futures).
    
    Args:
        args: Tuple containing (url, content, full_document)
        
    Returns:
        Tuple containing (contextual_text, was_contextualized)
    """
    url, content, full_document = args
    return contextualize_chunk(full_document, content) 