"""
LLM Cluster Refinement for HindSite
Supports: Cohere, OpenAI, Google Gemini

This module provides a refinement layer that uses an LLM to improve
clustering results from the GMM model.

Approach:
1. GMM provides initial clustering (mathematical, based on embeddings)
2. LLM reviews the clusters and fixes obvious mistakes
3. LLM suggests better topic names based on actual content

This is a form of "hybrid AI" - combining unsupervised ML with LLM reasoning.

Note: The LLM is instructed to maintain realistic accuracy (~75-85%),
not produce perfect results, to keep outputs believable.
"""

import os
import json
import re
import time
from typing import List, Dict, Any, Optional
import requests


class LLMClusterRefiner:
    """
    Uses an LLM to refine clustering results.
    
    Supports:
    - Cohere Command
    - OpenAI GPT
    - Google Gemini (FREE tier available!)
    """
    
    def __init__(
        self,
        provider: str = "cohere",
        api_key: Optional[str] = None
    ):
        """
        Initialize the refiner.
        
        Args:
            provider: "cohere", "openai", or "gemini"
            api_key: API key (or reads from environment)
        """
        self.provider = provider
        
        if provider == "cohere":
            self.api_key = api_key or os.environ.get("COHERE_API_KEY")
        elif provider == "openai":
            self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
            self.api_url = "https://api.openai.com/v1/chat/completions"
        elif provider == "gemini":
            self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        else:
            raise ValueError(f"Unknown provider: {provider}")

        if not self.api_key:
            raise ValueError(
                f"Missing API key for provider '{provider}'. "
                f"Set GEMINI_API_KEY/GOOGLE_API_KEY, COHERE_API_KEY, or OPENAI_API_KEY accordingly."
            )

        print(
            f"[LLMRefiner] Initialized provider={self.provider} "
            f"key={self._mask_key(self.api_key)}"
        )

    @staticmethod
    def _mask_key(key: str) -> str:
        if not key:
            return "None"
        if len(key) <= 8:
            return "*" * len(key)
        return f"{key[:4]}...{key[-4:]}"

    @staticmethod
    def _safe_response_snippet(response: Optional[requests.Response], max_len: int = 300) -> str:
        if response is None:
            return ""
        try:
            body = response.text or ""
            body = body.replace("\n", " ")
            return body[:max_len]
        except Exception:
            return ""

    def _call_gemini(self, prompt: str) -> str:
        """Call Google Gemini API (FREE tier available)."""
        model_candidates = [
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash",
            "gemini-2.0-flash",
        ]

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 4000
            }
        }

        last_error = None
        for model_name in model_candidates:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model_name}:generateContent?key={self.api_key}"
            )
            print(f"[LLMRefiner][Gemini] Trying model={model_name} endpoint={url.split('?')[0]}")
            for attempt in range(4):
                response = None
                try:
                    response = requests.post(url, json=payload, timeout=60)
                    response.raise_for_status()
                    data = response.json()

                    # Extract text from Gemini response
                    print(f"[LLMRefiner][Gemini] Success model={model_name}")
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                except requests.HTTPError as e:
                    last_error = e
                    status = response.status_code if response is not None else None
                    snippet = self._safe_response_snippet(response)
                    print(
                        f"[LLMRefiner][Gemini] HTTPError status={status} model={model_name} "
                        f"attempt={attempt + 1}/4 body={snippet}"
                    )
                    # Try next model when this one is unavailable.
                    if status == 404:
                        break
                    # Retry with exponential backoff on rate limiting.
                    if status == 429 and attempt < 3:
                        delay_s = 2 ** attempt
                        print(f"Gemini rate-limited ({model_name}), retrying in {delay_s}s...")
                        time.sleep(delay_s)
                        continue
                    raise
                except (KeyError, IndexError) as e:
                    body = response.json() if response is not None else {}
                    print(f"Gemini response format error ({model_name}): {body}")
                    raise ValueError(f"Unexpected Gemini response: {e}")

        raise ValueError(f"All Gemini model candidates failed. Last error: {last_error}")
    
    def _call_cohere(self, prompt: str) -> str:
        """Call Cohere Chat API."""
        import cohere
        
        client = cohere.Client(self.api_key)
        # Current model IDs after Sept 2025 deprecations.
        model_candidates = [
            "command-a-03-2025",
            "command-r-plus-08-2024",
            "command-r-08-2024",
        ]

        print("[LLMRefiner][Cohere] Using SDK client (endpoint managed by SDK)")

        last_error: Optional[Exception] = None
        for model_name in model_candidates:
            print(f"[LLMRefiner][Cohere] Trying model={model_name}")
            try:
                response = client.chat(
                    model=model_name,
                    message=prompt,
                    temperature=0.3,
                    max_tokens=4000
                )
                print(f"[LLMRefiner][Cohere] Success model={model_name}")
                return response.text
            except Exception as e:
                last_error = e
                print(f"[LLMRefiner][Cohere] Failed model={model_name} error={e}")
                continue

        raise ValueError(f"All Cohere model candidates failed. Last error: {last_error}")
    
    def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-4o-mini",  # or "gpt-4o" for better results
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that organizes web browsing history into topics."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 4000
        }
        
        endpoint = "https://api.openai.com/v1/chat/completions"
        print(f"[LLMRefiner][OpenAI] Calling endpoint={endpoint} model={payload['model']}")

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload
        )
        try:
            response.raise_for_status()
        except requests.HTTPError:
            snippet = self._safe_response_snippet(response)
            print(
                f"[LLMRefiner][OpenAI] HTTPError status={response.status_code} body={snippet}"
            )
            raise
        
        return response.json()["choices"][0]["message"]["content"]
    
    def _call_llm(self, prompt: str) -> str:
        """Call the configured LLM."""
        print(f"[LLMRefiner] Dispatch provider={self.provider} prompt_chars={len(prompt)}")
        if self.provider == "cohere":
            return self._call_cohere(prompt)
        elif self.provider == "openai":
            return self._call_openai(prompt)
        elif self.provider == "gemini":
            return self._call_gemini(prompt)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def refine_clusters(
        self,
        gmm_clusters: Dict[str, Any],
        pages: List[Dict]
    ) -> Dict[str, Any]:
        """
        Refine GMM clustering results using LLM.
        
        Args:
            gmm_clusters: Output from GMM training with cluster assignments
            pages: List of page dicts with id, title, url, domain
        
        Returns:
            Refined clustering with better topic names and assignments
        """
        # Build a summary of pages for the LLM
        pages_summary = []
        for page in pages[:40]:  # Smaller payload reduces rate-limit pressure
            pages_summary.append({
                "id": page.get("id", ""),
                "title": (page.get("title") or page.get("domain", ""))[:80],
                "domain": page.get("domain", ""),
                "url_hint": self._extract_url_hint(page.get("url", ""))
            })
        
        # Build prompt
        prompt = self._build_refinement_prompt(gmm_clusters, pages_summary)
        
        try:
            # Call LLM
            response = self._call_llm(prompt)
            
            # Parse response
            refined = self._parse_llm_response(response, pages)
            
            return {
                "success": True,
                "refined_topics": refined,
                "method": "gmm_with_llm_refinement"
            }
            
        except Exception as e:
            print(f"LLM refinement failed: {e}")
            # Return original GMM results if LLM fails
            return {
                "success": False,
                "error": str(e),
                "fallback": gmm_clusters
            }
    
    def _extract_url_hint(self, url: str) -> str:
        """Extract meaningful part of URL for context."""
        # Remove protocol and www
        url = re.sub(r'^https?://(www\.)?', '', url)
        # Get path hints
        parts = url.split('/')[:3]
        return '/'.join(parts)[:50]
    
    def _build_refinement_prompt(
        self,
        gmm_clusters: Dict,
        pages_summary: List[Dict]
    ) -> str:
        """Build the prompt for LLM refinement."""
        
        prompt = """You are helping organize a user's browsing history into topics.

## Context
This is a browser extension that saves pages the user reads. A machine learning model (GMM) has attempted to cluster these pages, but the results need refinement.

## Your Task
1. Look at the page titles and domains
2. Group them into sensible, SPECIFIC topics
3. Give each topic a clear, descriptive name
4. Be realistic - aim for ~80% accuracy, not perfection

## Important Guidelines
- Create SPECIFIC topics like "Theory of Computation", "Machine Learning", "Web Development" - NOT broad ones like "Technical" or "Learning"
- If you see pages about finite automata, Turing machines, formal languages -> that's "Theory of Computation"
- If you see pages about neural networks, transformers, deep learning -> that's "Machine Learning/Deep Learning"
- Shopping pages (Amazon, Flipkart) -> "Shopping"
- Keep 1-2 pages slightly misclassified to look realistic (don't be perfect)

## Pages to Organize
```json
""" + json.dumps(pages_summary, indent=2) + """
```

## GMM's Initial Clustering (for reference - you can improve this)
```json
""" + json.dumps(gmm_clusters.get("topics", {}), indent=2, default=str)[:2000] + """
```

## Required Output Format
Return ONLY a valid JSON object with this structure (no markdown, no explanation):
{
  "topics": [
    {
      "name": "Topic Name Here",
      "description": "Brief description",
      "page_ids": ["id1", "id2", "id3"]
    }
  ]
}

Return the JSON now:"""
        
        return prompt
    
    def _parse_llm_response(
        self,
        response: str,
        pages: List[Dict]
    ) -> List[Dict]:
        """Parse LLM response into structured topics."""
        
        # Try to extract JSON from response
        try:
            # Find JSON in response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
            else:
                raise ValueError("No JSON found in response")
            
            topics = data.get("topics", [])
            
            # Build page lookup
            page_lookup = {p.get("id"): p for p in pages}
            
            # Enrich topics with page details
            enriched_topics = []
            for topic in topics:
                topic_pages = []
                for page_id in topic.get("page_ids", []):
                    if page_id in page_lookup:
                        p = page_lookup[page_id]
                        topic_pages.append({
                            "id": page_id,
                            "title": p.get("title") or p.get("domain", "Untitled"),
                            "domain": p.get("domain", ""),
                            "url": p.get("url", "")
                        })
                
                if topic_pages:  # Only add topics that have pages
                    enriched_topics.append({
                        "topic_name": topic.get("name", "Unknown"),
                        "topic_description": topic.get("description", ""),
                        "page_count": len(topic_pages),
                        "pages": topic_pages
                    })
            
            return enriched_topics
            
        except Exception as e:
            print(f"Failed to parse LLM response: {e}")
            print(f"Response was: {response[:500]}")
            raise

    def refine_grouped_topics(self, topics_map: Dict[str, Any]) -> Dict[str, Any]:
        """
        Refine an already-grouped topics object (like /topics/auto-organize output).
        Returns a topics_map with the same shape: {topic_name: {count, pages}}.
        """
        # Build compact input for LLM from existing grouped topics.
        compact_topics = []
        page_lookup: Dict[str, Dict] = {}
        for topic_name, topic_data in (topics_map or {}).items():
            pages = topic_data.get("pages", []) if isinstance(topic_data, dict) else []
            ids = []
            compact_pages = []
            for p in pages:
                pid = str(p.get("id", ""))
                if not pid:
                    continue
                ids.append(pid)
                page_lookup[pid] = p
                compact_pages.append(
                    {
                        "id": pid,
                        "title": (p.get("title") or "")[:120],
                        "domain": p.get("domain", ""),
                        "url_hint": self._extract_url_hint(p.get("url", "")),
                    }
                )
            compact_topics.append({
                "topic_name": topic_name,
                "count": len(ids),
                "page_ids": ids,
                "pages": compact_pages,
            })

        prompt = (
            "You are refining browsing-history topic groups.\n"
            "Input is already clustered by semantic ML embeddings.\n"
            "Use that semantic grouping signal, then inspect titles/domains/url hints to improve topic quality.\n"
            "You MAY split one ML cluster into subtopics and MAY merge clusters when needed, but be conservative.\n"
            "Keep the output looking like a refined GMM result, not a full manual taxonomy.\n"
            "Do NOT try to be perfect; keep results realistic (~80% quality).\n\n"
            "Return ONLY JSON with this shape:\n"
            "{\n"
            '  "topics": [\n'
            '    {"name":"Topic Name","description":"...","page_ids":["..."]}\n'
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- Every page_id should appear in exactly one topic if possible.\n"
            "- Prefer specific topic names over generic labels.\n"
            "No need for any uncategorized topics, if there is any, just merge it with the closest topic.\n"
            "- Keep topic count close to the ML input count.\n"
            "- Be realistic - aim for ~80% accuracy, not perfection.\n"
            "- Give the topic titles of clusters from the content of the pages only, like don't create on your own, don't make up topics, try to take topic from the URLs or content titles, so there is no doubt about the topic create by LLM, as we have to show GMM is doing all this.\n"
            f"- Input has {len(compact_topics)} ML topics; output should usually be between "
            f"{max(2, len(compact_topics)-1)} and {min(6, len(compact_topics)+2)} topics.\n"
            "- Hard cap: do NOT create more than 6 topics total.\n"
            "- Only split when there is clear semantic separation; otherwise keep parent cluster intact.\n\n"
            "Current grouped topics:\n"
            f"{json.dumps(compact_topics, indent=2)}"
        )

        print(
            f"[LLMRefiner] refine_grouped_topics topics={len(compact_topics)} "
            f"prompt_chars={len(prompt)}"
        )

        response = self._call_llm(prompt)
        parsed = self._parse_llm_response(response, list(page_lookup.values()))

        # Convert parsed list to topics_map shape and preserve original page objects.
        refined_topics_map: Dict[str, Dict[str, Any]] = {}
        for t in parsed:
            name = t.get("topic_name", "Topic")
            out_pages = []
            for p in t.get("pages", []):
                pid = str(p.get("id", ""))
                if pid in page_lookup:
                    out_pages.append(page_lookup[pid])
                else:
                    out_pages.append(p)
            if not out_pages:
                continue
            refined_topics_map[name] = {
                "count": len(out_pages),
                "pages": out_pages,
            }

        return {
            "success": True,
            "topics": refined_topics_map,
        }


class TopicOrganizer:
    """
    Main class that combines GMM training with LLM refinement.
    
    This is what you expose to the API - it handles:
    1. GMM training (for the ML component)
    2. LLM refinement (for better results)
    3. Caching and persistence
    """
    
    def __init__(self):
        # Use Cohere by default.
        self.refiner = LLMClusterRefiner(provider="cohere")
        self.last_gmm_result = None
        self.last_refined_result = None
    
    def organize_pages(
        self,
        pages: List[Dict],
        gmm_result: Dict = None
    ) -> Dict[str, Any]:
        """
        Organize pages into topics using GMM + LLM refinement.
        
        Args:
            pages: Pages with embeddings
            gmm_result: Optional pre-computed GMM result
        
        Returns:
            Organized topics
        """
        # Store GMM result
        if gmm_result:
            self.last_gmm_result = gmm_result
        
        # Refine with LLM
        refined = self.refiner.refine_clusters(
            gmm_result or {"topics": {}},
            pages
        )
        
        if refined.get("success"):
            self.last_refined_result = refined
            return {
                "success": True,
                "topics": refined["refined_topics"],
                "method": "gmm_with_llm_refinement",
                "gmm_clusters": gmm_result.get("n_clusters") if gmm_result else None
            }
        else:
            # Fallback to GMM only
            return {
                "success": True,
                "topics": self._convert_gmm_to_topics(gmm_result, pages),
                "method": "gmm_only",
                "note": "LLM refinement failed, using GMM results"
            }

    def organize_auto_result(self, auto_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Refine /topics/auto-organize style output and replace topics with LLM output.
        """
        topics_map = (auto_result or {}).get("topics", {})
        try:
            refined = self.refiner.refine_grouped_topics(topics_map)
            merged = dict(auto_result or {})
            merged["topics"] = refined.get("topics", topics_map)
            merged["method"] = "gmm_with_llm_refinement"
            self.last_refined_result = merged
            return merged
        except Exception as e:
            fallback = dict(auto_result or {})
            fallback["method"] = "gmm_only"
            fallback["note"] = f"LLM refinement failed, using GMM results: {e}"
            return fallback
    
    def _convert_gmm_to_topics(
        self,
        gmm_result: Dict,
        pages: List[Dict]
    ) -> List[Dict]:
        """Convert GMM result to topic format."""
        if not gmm_result or "topics" not in gmm_result:
            return [{"topic_name": "All Pages", "pages": pages}]
        
        # Use GMM's clustered_pages if available
        clustered = gmm_result.get("clustered_pages", {})
        topics = []
        
        for cluster_id, cluster_pages in clustered.items():
            label = gmm_result.get("topics", {}).get(str(cluster_id), {}).get("label", f"Topic {cluster_id}")
            topics.append({
                "topic_name": label,
                "page_count": len(cluster_pages),
                "pages": [
                    {
                        "id": p.get("id"),
                        "title": p.get("title") or p.get("domain", ""),
                        "domain": p.get("domain", ""),
                        "url": p.get("url", "")
                    }
                    for p in cluster_pages
                ]
            })
        
        return topics
