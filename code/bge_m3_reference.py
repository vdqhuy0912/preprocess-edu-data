"""
BGE-M3 Reference Assignment Script

Assigns document chunk references to Q&A pairs using hybrid scoring:
Formula: final_score = 0.6 * cosine_sim(A, C) + 0.2 * cosine_sim(Q, C) + 0.2 * bm25_score

Model: BAAI/bge-m3 (Bi-Encoder)
"""

import json
import os
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple
import numpy as np
from tqdm import tqdm
import torch
import sys

# Using sentence-transformers for BGE-M3
from sentence_transformers import SentenceTransformer

# BM25
from rank_bm25 import BM25Okapi
import re

def setup_encoding():
    """Ensure utf-8 encoding for standard output on Windows."""
    if sys.stdout.encoding != 'utf-8':
        try:
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        except:
            pass

def load_reference_chunks(reference_dir: str) -> List[Dict[str, Any]]:
    """Load all chunks from reference JSON files."""
    chunks = []
    reference_path = Path(reference_dir)
    
    for json_file in reference_path.glob("*.json"):
        if not json_file.name.endswith('.json'):
            continue
            
        print(f"Loading: {json_file.name}")
        with open(json_file, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"Error loading {json_file.name}, skipping.")
                continue
        
        if 'chunks' in data:
            for chunk in data['chunks']:
                content = chunk.get('content', '')
                tables = chunk.get('tables', [])
                if not content.strip() and tables:
                    content = '\n'.join(tables)
                
                if content.strip():
                    chunks.append({
                        'source': json_file.name,
                        'chunk_id': chunk.get('chunk_id', len(chunks)),
                        'content': content.strip(),
                        'type': chunk.get('metadata', {}).get('type', 'text')
                    })
        
        elif 'chapters' in data:
            for chapter in data['chapters']:
                for article in chapter.get('articles', []):
                    article_title = article.get('article_title', '')
                    if article_title.strip():
                        chunks.append({
                            'source': json_file.name,
                            'chunk_id': f"article_{article.get('article_number', 'unknown')}",
                            'content': article_title.strip(),
                            'type': 'article_title'
                        })
                    
                    for clause in article.get('clauses', []):
                        content = clause.get('content', '')
                        tables = clause.get('latex_tables', [])
                        if not content.strip() and tables:
                            content = '\n'.join(tables)
                        
                        if content.strip():
                            chunks.append({
                                'source': json_file.name,
                                'chunk_id': f"article_{article.get('article_number')}_clause_{clause.get('clause_id', 'unknown')}",
                                'content': content.strip(),
                                'type': 'clause'
                            })
    
    print(f"Total chunks loaded: {len(chunks)}")
    return chunks

def tokenize_for_bm25(text: str) -> List[str]:
    text = text.lower()
    tokens = re.findall(r'\b\w+\b', text, re.UNICODE)
    return tokens

def normalize_bm25_scores(scores: np.ndarray) -> np.ndarray:
    if len(scores) == 0:
        return scores
    min_val = np.min(scores)
    max_val = np.max(scores)
    if max_val - min_val == 0:
        return np.zeros_like(scores)
    return (scores - min_val) / (max_val - min_val)

def assign_references(
    dialogs: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    model: SentenceTransformer,
    threshold: float = 0.5,
    top_k: int = 3
) -> List[Dict[str, Any]]:
    
    print("Computing chunk embeddings using BGE-M3...")
    chunk_contents = [c['content'] for c in chunks]
    # BGE-M3 handles large batches efficiently
    chunk_embeddings = model.encode(
        chunk_contents, 
        normalize_embeddings=True, 
        show_progress_bar=True,
        batch_size=16 # Adjust based on GPU memory
    )
    
    print("Building BM25 index...")
    tokenized_chunks = [tokenize_for_bm25(c) for c in chunk_contents]
    bm25_index = BM25Okapi(tokenized_chunks)
    
    results = []
    
    for dialog in tqdm(dialogs, desc="Processing dialogs"):
        dialog_copy = dialog.copy()
        
        messages = dialog.get('messages', [])
        question = ""
        answer = ""
        for msg in messages:
            if msg.get('role') == 'user':
                question = msg.get('content', '')
            elif msg.get('role') == 'assistant':
                answer = msg.get('content', '')
        
        if not question or not answer:
            dialog_copy['reference'] = []
            results.append(dialog_copy)
            continue
            
        # 1. Compute Question and Answer embeddings
        q_emb = model.encode(question, normalize_embeddings=True)
        a_emb = model.encode(answer, normalize_embeddings=True)
        
        # 2. Cosine similarities (dot product since normalized)
        cosine_a_c = np.dot(chunk_embeddings, a_emb)
        cosine_q_c = np.dot(chunk_embeddings, q_emb)
        
        # 3. BM25 score
        query_tokens = tokenize_for_bm25(f"{question} {answer}")
        bm25_scores = np.array(bm25_index.get_scores(query_tokens))
        bm25_scores_norm = normalize_bm25_scores(bm25_scores)
        
        # 4. Final score formula
        # final_score = 0.6 * cos(A,C) + 0.2 * cos(Q,C) + 0.2 * BM25
        final_scores = (
            0.6 * cosine_a_c +
            0.2 * cosine_q_c +
            0.2 * bm25_scores_norm
        )
        
        # Get top-K above threshold
        top_indices = np.argsort(final_scores)[::-1][:top_k]
        
        references = []
        for idx in top_indices:
            score = float(final_scores[idx])
            if score >= threshold:
                chunk = chunks[idx]
                references.append({
                    'source': chunk['source'],
                    'chunk_id': chunk['chunk_id'],
                    'content': chunk['content'],
                    'score': round(score, 4)
                })
        
        dialog_copy['reference'] = references
        results.append(dialog_copy)
        
    return results

def main():
    setup_encoding()
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=str, required=True)
    parser.add_argument('--output', type=str, required=True)
    parser.add_argument('--reference_dir', type=str, default='data/references')
    parser.add_argument('--threshold', type=float, default=0.5)
    parser.add_argument('--top_k', type=int, default=3)
    parser.add_argument('--model', type=str, default='BAAI/bge-m3')
    
    args = parser.parse_args()
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    
    print(f"Loading model {args.model}...")
    model = SentenceTransformer(args.model, device=device)
    
    chunks = load_reference_chunks(args.reference_dir)
    
    with open(args.input, 'r', encoding='utf-8') as f:
        dialogs = json.load(f)
    print(f"Total dialogs: {len(dialogs)}")
    
    results = assign_references(
        dialogs=dialogs,
        chunks=chunks,
        model=model,
        threshold=args.threshold,
        top_k=args.top_k
    )
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"Done! Results saved to {args.output}")

if __name__ == '__main__':
    main()
