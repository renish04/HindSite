# HindSite Topic Classification System

This document explains how to set up, run, and test the ML-based topic classification system.

## Overview

The topic classification system uses Gaussian Mixture Models (GMM) to discover natural topic clusters in your browsing history. It's completely unsupervised - no predefined categories needed.

## Prerequisites

1. **Python Dependencies**
```bash
   pip install scikit-learn numpy
```

2. **Backend Running**
```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

3. **Database with Pages**
   You need at least 20 captured pages with embeddings to train the model.

## Quick Start

### Option 1: API Endpoints

1. **Check Status**
```bash
   curl http://localhost:8000/topics/status
```

2. **Train the Model**
```bash
   curl -X POST http://localhost:8000/topics/train \
        -H "Content-Type: application/json" \
        -d '{"force_retrain": false}'
```

3. **Get Organized Pages**
```bash
   curl http://localhost:8000/topics/pages
```

4. **Auto-Organize (Train if needed + Organize)**
```bash
   curl -X POST http://localhost:8000/topics/auto-organize
```

### Option 2: Python Script

Create a test script `test_topics.py`:
```python
"""
Test script for the topic classification system.
Run this to verify everything is working.
"""

import requests
import json

API_BASE = "http://localhost:8000"

def test_status():
    """Check model status."""
    print("\n=== Model Status ===")
    response = requests.get(f"{API_BASE}/topics/status")
    data = response.json()
    print(json.dumps(data, indent=2))
    return data

def test_train(force=False):
    """Train the model."""
    print("\n=== Training Model ===")
    response = requests.post(
        f"{API_BASE}/topics/train",
        json={"force_retrain": force}
    )
    data = response.json()
    print(json.dumps(data, indent=2))
    return data

def test_get_pages():
    """Get pages organized by topic."""
    print("\n=== Pages by Topic ===")
    response = requests.get(f"{API_BASE}/topics/pages")
    data = response.json()
    
    for topic in data:
        print(f"\n📁 {topic['topic_label']} ({topic['page_count']} pages)")
        for page in topic['pages'][:3]:  # Show first 3
            print(f"   • {page['title'][:50]}...")
    
    return data

def test_auto_organize():
    """Auto-organize pages."""
    print("\n=== Auto-Organizing ===")
    response = requests.post(f"{API_BASE}/topics/auto-organize")
    data = response.json()
    print(json.dumps(data, indent=2))
    return data

def test_classify_page(page_id):
    """Classify a single page."""
    print(f"\n=== Classifying Page {page_id} ===")
    response = requests.post(f"{API_BASE}/topics/classify/{page_id}")
    data = response.json()
    print(json.dumps(data, indent=2))
    return data

if __name__ == "__main__":
    print("=" * 60)
    print("TOPIC CLASSIFICATION SYSTEM TEST")
    print("=" * 60)
    
    # 1. Check status
    status = test_status()
    
    # 2. Train if not trained
    if not status.get("is_trained"):
        print("\nModel not trained. Training now...")
        test_train(force=True)
    
    # 3. Get organized pages
    test_get_pages()
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
```

Run with:
```bash
python test_topics.py
```

## How It Works

### Training Flow

1. **Fetch Pages**: Get all pages with embeddings from database
2. **Preprocess**: Standardize and reduce dimensions (PCA: 1024 → 50)
3. **Model Selection**: Try K=2,3,4...10 clusters, pick best using BIC
4. **Train GMM**: Run EM algorithm to find cluster centers and shapes
5. **Label Topics**: Generate names from page titles and domains
6. **Save Model**: Persist to disk for future use

### Classification Flow

1. **Load Model**: Load trained model from disk (if not in memory)
2. **Preprocess**: Apply same scaling and PCA as training
3. **Compute Probabilities**: Calculate probability for each topic
4. **Check Outlier**: If best probability < 15%, mark as outlier
5. **Return Result**: Topic label, confidence, all probabilities

### Outlier Handling

When a page doesn't fit any topic well:
1. It's marked as "outlier"
2. Added to outlier buffer
3. When 5+ outliers accumulate → triggers retraining
4. Retraining may discover a new topic cluster

## API Reference

### POST /topics/train
Train or retrain the model.

**Request:**
```json
{
  "force_retrain": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Successfully trained model with 5 topics",
  "n_topics": 5,
  "pages_trained": 87,
  "topics": {
    "0": {
      "label": "Machine & Learning & Python",
      "page_count": 23,
      "top_words": ["machine", "learning", "python", "model", "data"],
      "top_domains": ["arxiv.org", "github.com", "medium.com"]
    },
    ...
  }
}
```

### GET /topics/pages
Get all pages organized by topic.

**Response:**
```json
[
  {
    "topic_label": "Machine & Learning & Python",
    "page_count": 23,
    "pages": [
      {
        "id": "abc123",
        "url": "https://example.com/ml-tutorial",
        "title": "Machine Learning Tutorial",
        "domain": "example.com",
        "topic_confidence": 0.87,
        "is_outlier": false
      },
      ...
    ]
  },
  ...
]
```

### POST /topics/classify/{page_id}
Classify a single page.

**Response:**
```json
{
  "success": true,
  "page_id": "abc123",
  "topic_label": "Machine & Learning & Python",
  "confidence": 0.87,
  "is_outlier": false,
  "all_probabilities": {
    "Machine & Learning & Python": 0.87,
    "Web & Development & React": 0.08,
    "News & Technology": 0.05
  }
}
```

## Troubleshooting

### "Need at least 20 pages"
- Capture more pages by browsing with the extension
- Each page needs 60s reading time + 40% scroll

### "Model not trained"
- Call `/topics/train` or click "Auto-Organize" button

### Topics don't make sense
- Try retraining with `force_retrain: true`
- The model learns from YOUR browsing - it reflects your interests

### Classification is slow
- First classification loads model from disk (one-time)
- Subsequent classifications are fast (~10ms)

## The Math (Simplified)

**GMM Training (EM Algorithm):**
1. Start with random topic centers
2. E-step: For each page, compute "how much does each topic explain this page?"
3. M-step: Move topic centers to weighted average of their pages
4. Repeat until centers stop moving

**Classification:**
- Compute distance from page to each topic center
- Account for topic "shape" (some topics are spread out, some are tight)
- Return probability distribution over topics

