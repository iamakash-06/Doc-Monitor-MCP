"""
Advanced document ingestion pipeline for the doc-monitor MCP server.
Handles document routing, adaptive chunking, and content processing.
"""
from typing import Dict, Any, Optional, List
from enum import Enum
import re
import mimetypes
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. Smart Document Router
# ==============================================================================

class DocumentType(Enum):
    """Enumeration for different document types."""
    OPENAPI = "openapi"
    SWAGGER = "swagger"
    MARKDOWN = "markdown"
    LLMS_TXT = "llms_txt"
    SITEMAP = "sitemap"
    WEBPAGE = "webpage"
    TEXT = "text"

class DocumentRouter:
    """
    Intelligently detects document types based on URL patterns, content-type headers,
    and content inspection to route documents to appropriate processing pipelines.
    """
    
    def __init__(self):
        self.url_patterns = {
            DocumentType.OPENAPI: [
                r'.*/(openapi|swagger).*\.(json|yaml|yml)$',
                r'.*/api-docs.*$',
                r'.*/v[0-9]+/.*\.(json|yaml|yml)$'
            ],
            DocumentType.SWAGGER: [
                r'.*/swagger.*\.(json|yaml|yml)$',
                r'.*/swagger-ui.*$'
            ],
            DocumentType.LLMS_TXT: [
                r'.*/llms\.txt$',
                r'.*/\.well-known/llms\.txt$'
            ],
            DocumentType.MARKDOWN: [
                r'.*\.md$',
                r'.*\.markdown$',
                r'.*/README.*$'
            ],
            DocumentType.SITEMAP: [
                r'.*/sitemap.*\.xml$',
                r'.*/sitemap.*\.txt$'
            ]
        }
        
    def detect_document_type(self, url: str, content_type: Optional[str] = None, content: Optional[str] = None) -> DocumentType:
        """
        Detect document type using multiple strategies.
        
        Args:
            url: The document URL
            content_type: Optional HTTP content-type header
            content: Optional document content for inspection
            
        Returns:
            Detected DocumentType
        """
        logger.debug(f"🔍 Detecting document type for: {url}")
        
        # Strategy 1: URL pattern matching
        url_lower = url.lower()
        for doc_type, patterns in self.url_patterns.items():
            for pattern in patterns:
                if re.match(pattern, url_lower):
                    logger.debug(f"✅ Matched URL pattern {pattern} -> {doc_type.value}")
                    return doc_type
        
        # Strategy 2: Content-type detection
        if content_type:
            content_type_lower = content_type.lower()
            if 'application/json' in content_type_lower or 'application/yaml' in content_type_lower:
                if 'openapi' in url_lower or 'swagger' in url_lower:
                    return DocumentType.OPENAPI
            elif 'text/xml' in content_type_lower or 'application/xml' in content_type_lower:
                if 'sitemap' in url_lower:
                    return DocumentType.SITEMAP
            elif 'text/markdown' in content_type_lower:
                return DocumentType.MARKDOWN
        
        # Strategy 3: Content inspection (if provided)
        if content:
            content_preview = content[:500].lower()
            if any(keyword in content_preview for keyword in ['openapi', 'swagger', '"info":', '"paths":']):
                return DocumentType.OPENAPI
            elif content_preview.startswith('# ') or '## ' in content_preview:
                return DocumentType.MARKDOWN
            elif '<sitemap' in content_preview or '<urlset' in content_preview:
                return DocumentType.SITEMAP
        
        # Default to webpage
        logger.debug(f"🔄 No specific type detected, defaulting to webpage")
        return DocumentType.WEBPAGE

# ==============================================================================
# 2. Adaptive Chunking System
# ==============================================================================

class AdaptiveChunker:
    """
    Simple but effective semantic chunker that splits text into coherent chunks.
    This is a fallback implementation that doesn't require external dependencies.
    """

    def __init__(self, 
                 max_chunk_size: int = 2000, 
                 min_chunk_size: int = 100,
                 overlap_size: int = 200):
        """
        Initialize the chunker with size parameters.
        
        Args:
            max_chunk_size: Maximum size of each chunk in characters
            min_chunk_size: Minimum size of each chunk in characters  
            overlap_size: Overlap size between chunks
        """
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap_size = overlap_size
        logger.debug(f"🧩 AdaptiveChunker initialized: max={max_chunk_size}, min={min_chunk_size}, overlap={overlap_size}")

    def semantic_chunk(self, text: str) -> List[str]:
        """
        Split text into semantically coherent chunks using smart boundary detection.
        
        Args:
            text: Input text to chunk
            
        Returns:
            List of text chunks
        """
        logger.debug(f"🧩 Chunking text: {len(text)} characters")
        
        if not text or len(text.strip()) < self.min_chunk_size:
            logger.debug(f"⚠️ Text too short, returning as single chunk")
            return [text.strip()] if text.strip() else []
        
        chunks = []
        
        # Strategy 1: Split by major section headers (Markdown style)
        major_sections = self._split_by_headers(text)
        
        for section in major_sections:
            if len(section) <= self.max_chunk_size:
                chunks.append(section.strip())
            else:
                # Strategy 2: Split large sections by paragraphs and sentences
                sub_chunks = self._split_by_paragraphs_and_sentences(section)
                chunks.extend(sub_chunks)
        
        # Clean up and add overlap
        final_chunks = self._add_overlap_and_clean(chunks)
        
        logger.debug(f"✅ Created {len(final_chunks)} chunks")
        return final_chunks

    def _split_by_headers(self, text: str) -> List[str]:
        """Split text by major section headers."""
        # Match markdown headers (# ## ###) and common section patterns
        header_pattern = r'\n(?=#+\s|\n[A-Z][^a-z]*\n|(?:Introduction|Overview|Getting Started|API|Usage|Example|Reference|Conclusion))'
        
        sections = re.split(header_pattern, text)
        return [section for section in sections if section.strip()]

    def _split_by_paragraphs_and_sentences(self, text: str) -> List[str]:
        """Split large text by paragraphs and sentences while respecting boundaries."""
        chunks = []
        current_chunk = ""
        
        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
                
            # If adding this paragraph would exceed max size, save current chunk
            if len(current_chunk) + len(paragraph) > self.max_chunk_size and current_chunk:
                if len(current_chunk.strip()) >= self.min_chunk_size:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
            
            # If even a single paragraph is too large, split by sentences
            if len(current_chunk) > self.max_chunk_size:
                sentence_chunks = self._split_by_sentences(current_chunk)
                if len(sentence_chunks) > 1:
                    chunks.extend(sentence_chunks[:-1])  # Add all but last
                    current_chunk = sentence_chunks[-1]  # Keep last for next iteration
        
        # Add final chunk
        if current_chunk and len(current_chunk.strip()) >= self.min_chunk_size:
            chunks.append(current_chunk.strip())
        
        return chunks

    def _split_by_sentences(self, text: str) -> List[str]:
        """Split text by sentences while maintaining semantic coherence."""
        # Simple sentence splitting (can be improved with more sophisticated NLP)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= self.max_chunk_size:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks

    def _add_overlap_and_clean(self, chunks: List[str]) -> List[str]:
        """Add overlap between chunks and clean up."""
        if len(chunks) <= 1:
            return chunks
        
        final_chunks = []
        
        for i, chunk in enumerate(chunks):
            if i == 0:
                # First chunk - no overlap needed
                final_chunks.append(chunk)
            else:
                # Add overlap from previous chunk
                prev_chunk = chunks[i-1]
                overlap_text = prev_chunk[-self.overlap_size:] if len(prev_chunk) > self.overlap_size else prev_chunk
                
                # Find a good breaking point for overlap (end of sentence if possible)
                break_points = [m.end() for m in re.finditer(r'[.!?]\s+', overlap_text)]
                if break_points:
                    overlap_text = overlap_text[break_points[-1]:]
                
                overlapped_chunk = overlap_text + "\n\n" + chunk
                final_chunks.append(overlapped_chunk)
        
        return [chunk for chunk in final_chunks if len(chunk.strip()) >= self.min_chunk_size] 