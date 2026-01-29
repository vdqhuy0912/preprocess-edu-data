"""
Hybrid Reference Assignment Script (PA2)

Assigns document chunk references to Q&A pairs using Reranker-based hybrid scoring:
Formula: final_score = 0.6 * Sigmoid(Reranker(A, C)) + 0.2 * Sigmoid(Reranker(Q, C)) + 0.2 * BM25_score

Models:
- Reranker: BAAI/bge-reranker-base
- BM25: rank_bm25
"""

import json
import os
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple
import numpy as np
from tqdm import tqdm
import torch

# Using transformers for Reranker
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# BM25
from rank_bm25 import BM25Okapi
import re


def load_reference_chunks(reference_dir: str) -> List[Dict[str, Any]]:
    """Load all chunks from reference JSON files."""
    chunks = []
    reference_path = Path(reference_dir)
    
    import sys
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            # Fallback for older python
            pass

    for json_file in reference_path.glob("*.json"):
        # Skip docx files and other non-json
        if not json_file.name.endswith('.json'):
            continue
            
        print(f"Loading: {json_file.name}")
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle different JSON structures
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


def normalize_scores(scores: np.ndarray) -> np.ndarray:
    if len(scores) == 0:
        return scores
    min_val = np.min(scores)
    max_val = np.max(scores)
    if max_val - min_val == 0:
        return np.zeros_like(scores)
    return (scores - min_val) / (max_val - min_val)


class BGEReranker:
    def __init__(self, model_name: str, device: str = None):
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
            
        print(f"Loading reranker model {model_name} on {self.device}...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()

    def score_pairs(self, pairs: List[Tuple[str, str]], batch_size: int = 32) -> np.ndarray:
        all_logits = []
        with torch.no_grad():
            for i in range(0, len(pairs), batch_size):
                batch = pairs[i:i+batch_size]
                inputs = self.tokenizer(batch, padding=True, truncation=True, return_tensors='pt', max_length=512)
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
                logits = self.model(**inputs).logits.view(-1).cpu().float()
                all_logits.append(logits)
        
        logits_concat = torch.cat(all_logits).numpy()
        # Sigmoid to normalize to [0, 1]
        return 1 / (1 + np.exp(-logits_concat))


def assign_references(
    dialogs: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    reranker: BGEReranker,
    threshold: float = 0.5,
    top_k: int = 3
) -> List[Dict[str, Any]]:
    
    print("Building BM25 index...")
    chunk_contents = [c['content'] for c in chunks]
    tokenized_chunks = [tokenize_for_bm25(c) for c in chunk_contents]
    bm25_index = BM25Okapi(tokenized_chunks)
    
    results = []
    
    for dialog in tqdm(dialogs, desc="Processing dialogs"):
        dialog_copy = dialog.copy()
        
        # Extract Q and A
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
            
        # 1. BM25 score
        query_tokens = tokenize_for_bm25(f"{question} {answer}")
        bm25_scores = np.array(bm25_index.get_scores(query_tokens))
        bm25_scores_norm = normalize_scores(bm25_scores)
        
        # 2. Reranker scores for (A, C) and (Q, C)
        # To optimize, we only rerank top N candidates from BM25 if the full set is too large
        # But here let's try with all if feasible, or pick top 100 to save time
        candidate_indices = np.argsort(bm25_scores)[-200:] # Pick top 200 candidates to rerank
        
        pairs_a_c = [(answer, chunk_contents[idx]) for idx in candidate_indices]
        pairs_q_c = [(question, chunk_contents[idx]) for idx in candidate_indices]
        
        scores_a_c = reranker.score_pairs(pairs_a_c)
        scores_q_c = reranker.score_pairs(pairs_q_c)
        
        # Combine
        # final_score = 0.6 * S_AC + 0.2 * S_QC + 0.2 * BM25_NORM
        final_scores_candidates = (
            0.6 * scores_a_c +
            0.2 * scores_q_c +
            0.2 * bm25_scores_norm[candidate_indices]
        )
        
        # Sort candidates
        sorted_cand_idx = np.argsort(final_scores_candidates)[::-1]
        
        references = []
        for i in sorted_cand_idx[:top_k]:
            score = float(final_scores_candidates[i])
            if score >= threshold:
                orig_idx = candidate_indices[i]
                chunk = chunks[orig_idx]
                references.append({
                    'source': chunk['source'],
                    'chunk_id': chunk['chunk_id'],
                    'content': chunk['content'][:500] + ('...' if len(chunk['content']) > 500 else ''),
                    'score': round(score, 4)
                })
        
        dialog_copy['reference'] = references
        results.append(dialog_copy)
        
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=str, required=True)
    parser.add_argument('--output', type=str, required=True)
    parser.add_argument('--reference_dir', type=str, default='data/references')
    parser.add_argument('--threshold', type=float, default=0.5)
    parser.add_argument('--top_k', type=int, default=3)
    parser.add_argument('--model', type=str, default='BAAI/bge-reranker-base')
    
    args = parser.parse_args()
    
    reranker = BGEReranker(args.model)
    chunks = load_reference_chunks(args.reference_dir)
    
    with open(args.input, 'r', encoding='utf-8') as f:
        dialogs = json.load(f)
        
    results = assign_references(
        dialogs=dialogs,
        chunks=chunks,
        reranker=reranker,
        threshold=args.threshold,
        top_k=args.top_k
    )
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"Done! Results saved to {args.output}")


if __name__ == '__main__':
    main()
