"""
Document processing and text operations for the doc-monitor MCP server.
Handles text chunking, metadata extraction, and document processing.
"""
import re
import asyncio
from typing import List, Dict, Any
from urllib.parse import urlparse


def smart_chunk_markdown(text: str, chunk_size: int = 5000) -> List[str]:
    """
    Split text into chunks, respecting code blocks and paragraphs.
    
    Args:
        text: The text to chunk
        chunk_size: Target size for each chunk
        
    Returns:
        List of text chunks
    """
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = start + chunk_size
        
        if end >= text_length:
            chunks.append(text[start:].strip())
            break
        
        chunk = text[start:end]
        
        # Try to find good split points
        # 1. Code block boundaries
        code_block = chunk.rfind('```')
        if code_block != -1 and code_block > chunk_size * 0.3:
            end = start + code_block
        # 2. Paragraph breaks
        elif '\n\n' in chunk:
            last_break = chunk.rfind('\n\n')
            if last_break > chunk_size * 0.3:
                end = start + last_break
        # 3. Sentence boundaries
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
    """
    Extract headers and stats from a markdown chunk.
    
    Args:
        chunk: The text chunk to analyze
        
    Returns:
        Dictionary containing section information
    """
    headers = re.findall(r'^(#+)\s+(.+)$', chunk, re.MULTILINE)
    header_str = '; '.join(f'{h[0]} {h[1]}' for h in headers) if headers else ''
    
    return {
        "headers": header_str,
        "char_count": len(chunk),
        "word_count": len(chunk.split())
    }


def build_metadata(chunk: str, i: int, url: str, crawl_type: str = None, version: int = 1) -> Dict[str, Any]:
    """
    Build metadata for a document chunk.
    
    Args:
        chunk: The text chunk
        i: Chunk index
        url: Source URL
        crawl_type: Type of crawl operation
        version: Document version
        
    Returns:
        Metadata dictionary
    """
    meta = extract_section_info(chunk)
    meta.update({
        "chunk_index": i,
        "url": url,
        "source": urlparse(url).netloc,
        "version": version,
        "crawl_time": str(asyncio.current_task().get_coro().__name__) if asyncio.current_task() else "unknown"
    })
    
    if crawl_type:
        meta["crawl_type"] = crawl_type
        
    return meta


def analyze_change_impact(change: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze the impact of a change and provide recommendations.
    
    Args:
        change: Dictionary containing change information
        
    Returns:
        Analysis results with severity and recommendations
    """
    analysis = {
        "severity": change.get("change_impact", "low"),
        "recommendations": [],
        "breaking_changes": False,
        "api_changes": False
    }
    
    old_content = change.get("change_details", {}).get("old_content", "") or ""
    new_content = change.get("change_details", {}).get("new_content", "") or ""
    
    # API change patterns
    api_patterns = [
        r"api\s+endpoint", r"api\s+version", r"request\s+parameters", r"response\s+format",
        r"http\s+method", r"authentication", r"headers", r"query\s+parameters"
    ]
    
    # Breaking change patterns
    breaking_patterns = [
        r"breaking\s+change", r"deprecated", r"removed", r"no longer supported", 
        r"changed from", r"replaced by"
    ]
    
    # Check for API changes
    for pattern in api_patterns:
        if re.search(pattern, new_content, re.IGNORECASE):
            analysis["api_changes"] = True
            analysis["recommendations"].append(
                "API changes detected. Review API documentation and update client code if necessary."
            )
            break
    
    # Check for breaking changes
    for pattern in breaking_patterns:
        if re.search(pattern, new_content, re.IGNORECASE):
            analysis["breaking_changes"] = True
            analysis["severity"] = "high"
            analysis["recommendations"].append(
                "Breaking changes detected. Immediate action required to update dependent systems."
            )
            break
    
    # Add recommendations based on change type
    change_type = change.get("change_type", "unknown")
    if change_type == "added":
        analysis["recommendations"].append("New content added. Review for new features or functionality.")
    elif change_type == "deleted":
        analysis["recommendations"].append("Content removed. Check if removed functionality needs to be replaced.")
    elif change_type == "modified":
        analysis["recommendations"].append("Content modified. Review changes for impact on existing functionality.")
    
    return analysis 