"""Module 2 — Historical Defect Knowledge Base + RAG ingestion pipeline.

Flow:  raw dataset  ->  DefectRecord (normalize)  ->  clean  ->  chunk
       ->  sentence-transformers embeddings  ->  Chroma index.
"""
