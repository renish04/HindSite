"""
HindSite Topic Discovery System

This module implements personalized topic discovery using Gaussian Mixture Models.
It learns topic structure from the user's own browsing history without requiring
any predefined categories or labeled data.

The system:
1. Learns topics from existing pages (training)
2. Classifies new pages into learned topics (inference)
3. Detects outliers that don't fit existing topics
4. Dynamically creates new topics when needed
5. Periodically retrains to adapt to changing interests

This is UNSUPERVISED MACHINE LEARNING - we discover structure from data,
not from labels.
"""

import numpy as np
from sklearn.decomposition import PCA
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler
from collections import Counter
from typing import List, Dict, Tuple, Optional, Any, Set
from datetime import datetime
import json
import os
import pickle
import re


class TopicModel:
    """
    Gaussian Mixture Model based topic discovery for browsing history.
    
    This class handles:
    - Training: Learning topic clusters from page embeddings
    - Inference: Classifying new pages into topics
    - Outlier detection: Identifying pages that don't fit any topic
    - Dynamic adaptation: Creating new topics and retraining
    
    The model is personalized - it learns from each user's specific browsing patterns.
    """
    
    def __init__(
        self,
        n_components_pca: int = 50,
        min_clusters: int = 2,
        max_clusters: int = 10,
        outlier_threshold: float = 0.15,
        min_pages_for_training: int = 20,
        model_save_path: str = "./trained_models"
    ):
        """
        Initialize the Topic Model.
        
        Args:
            n_components_pca: Number of dimensions to reduce to (default 50).
                             Lower = faster but might lose information.
                             Higher = slower but more accurate.
            
            min_clusters: Minimum number of topic clusters to try (default 2).
            
            max_clusters: Maximum number of topic clusters to try (default 10).
                         We'll test each value and pick the best using BIC.
            
            outlier_threshold: If a page's best cluster probability is below this,
                              it's considered an outlier that doesn't fit any topic.
                              Default 0.15 (15% probability).
            
            min_pages_for_training: Minimum pages needed before we can train.
                                   Default 20 pages.
            
            model_save_path: Directory to save/load trained models.
        """
        self.n_components_pca = n_components_pca
        self.min_clusters = min_clusters
        self.max_clusters = max_clusters
        self.outlier_threshold = outlier_threshold
        self.min_pages_for_training = min_pages_for_training
        self.model_save_path = model_save_path
        
        # These get set during training
        self.pca: Optional[PCA] = None
        self.scaler: Optional[StandardScaler] = None
        self.gmm: Optional[GaussianMixture] = None
        self.n_clusters: int = 0
        self.topic_labels: Dict[int, str] = {}
        self.topic_metadata: Dict[int, Dict] = {}
        self.cluster_confidence_stats: Dict[int, Dict[str, float]] = {}
        self.is_trained: bool = False
        self.training_timestamp: Optional[datetime] = None
        self.pages_at_training: int = 0
        
        # Outlier buffer - pages that didn't fit any cluster
        # When enough outliers accumulate, we might form a new cluster
        self.outlier_buffer: List[Dict] = []
        self.outliers_for_new_cluster: int = 5  # Create new cluster after 5 outliers
        
        # Create model save directory if it doesn't exist
        os.makedirs(model_save_path, exist_ok=True)
    
    def _preprocess_embeddings(
        self, 
        embeddings: List[List[float]], 
        fit: bool = False
    ) -> np.ndarray:
        """
        Preprocess embeddings for GMM training/inference.
        
        This does two things:
        1. Standardize (zero mean, unit variance) - important for GMM
        2. Reduce dimensions with PCA (1024 -> 50) - faster and more stable
        
        Args:
            embeddings: List of 1024-dimensional embedding vectors
            fit: If True, fit the scaler and PCA (during training)
                 If False, use already-fitted transformers (during inference)
        
        Returns:
            Preprocessed embeddings as numpy array (N x 50)
        """
        # Use float64 for numerical stability in GMM/Cholesky
        X = np.array(embeddings, dtype=np.float64)
        
        if fit:
            # Fit and transform during training
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X)
            
            # Determine PCA components (can't have more than samples or features)
            n_components = min(self.n_components_pca, X.shape[0], X.shape[1])
            self.pca = PCA(n_components=n_components)
            X_reduced = self.pca.fit_transform(X_scaled)
            
            print(f"PCA: Reduced {X.shape[1]} dims to {X_reduced.shape[1]} dims")
            print(f"PCA: Explained variance ratio: {sum(self.pca.explained_variance_ratio_):.2%}")
        else:
            # Transform only during inference (using fitted scaler/PCA)
            if self.scaler is None or self.pca is None:
                raise ValueError("Model not trained. Call train() first.")
            X_scaled = self.scaler.transform(X)
            X_reduced = self.pca.transform(X_scaled)
        
        return X_reduced

    def _calibrate_confidence(self, cluster_id: int, raw_probability: float, log_density: float) -> float:
        """
        Convert raw GMM posterior into a more user-facing confidence score.
        Uses both posterior probability and how typical the point is within
        the predicted cluster based on training log-density percentiles.
        """
        stats = self.cluster_confidence_stats.get(cluster_id)
        if not stats:
            return float(raw_probability)

        lo = stats.get("p05", stats.get("min", log_density))
        hi = stats.get("p95", stats.get("max", log_density))
        if hi <= lo:
            density_score = 0.5
        else:
            density_score = (log_density - lo) / (hi - lo)
            density_score = float(np.clip(density_score, 0.0, 1.0))

        # Keep posterior dominant; density only refines confidence slightly.
        calibrated = 0.85 * raw_probability + 0.15 * density_score
        return float(np.clip(calibrated, 0.0, 0.995))

    def _fit_gmm(self, X: np.ndarray, n_components: int) -> GaussianMixture:
        """
        Fit a GaussianMixture with stability-focused settings.

        For small datasets (or near-duplicate embeddings), GMM can hit singular /
        non-positive-definite covariance matrices. We regularize covariances and
        fall back to a more stable covariance_type if needed.
        """
        # Primary attempt: full covariance + small regularization
        try:
            gmm = GaussianMixture(
                n_components=n_components,
                covariance_type="full",
                reg_covar=1e-6,
                n_init=5,
                max_iter=300,
                random_state=42,
                init_params="kmeans",
            )
            gmm.fit(X)
            return gmm
        except Exception:
            # Fallback: diagonal covariance + stronger regularization
            gmm = GaussianMixture(
                n_components=n_components,
                covariance_type="diag",
                reg_covar=1e-4,
                n_init=5,
                max_iter=300,
                random_state=42,
                init_params="kmeans",
            )
            gmm.fit(X)
            return gmm
    
    def _find_optimal_clusters(self, X: np.ndarray) -> int:
        """
        Find the optimal number of clusters using Bayesian Information Criterion (BIC).
        
        BIC balances model fit against model complexity:
        - More clusters = better fit to data
        - But more clusters = more parameters = higher penalty
        - BIC finds the sweet spot
        
        Lower BIC is better.
        
        Args:
            X: Preprocessed embeddings (N x reduced_dims)
        
        Returns:
            Optimal number of clusters
        """
        n_samples = X.shape[0]
        
        # Adjust range based on sample size
        max_k = min(self.max_clusters, n_samples // 3)  # Need at least 3 samples per cluster
        max_k = max(max_k, self.min_clusters)
        
        print(f"Testing cluster counts from {self.min_clusters} to {max_k}...")
        
        bic_scores = {}
        
        for k in range(self.min_clusters, max_k + 1):
            try:
                gmm = self._fit_gmm(X, k)
                bic = gmm.bic(X)
                bic_scores[k] = bic
                print(f"  K={k}: BIC = {bic:.2f}")
            except Exception as e:
                print(f"  K={k}: Failed ({e})")
                continue
        
        if not bic_scores:
            print("Warning: Could not fit any GMM. Defaulting to 2 clusters.")
            return 2
        
        # Find K with lowest BIC
        optimal_k = min(bic_scores, key=bic_scores.get)
        print(f"Optimal number of clusters: {optimal_k} (BIC: {bic_scores[optimal_k]:.2f})")
        
        return optimal_k
    
    def _generate_topic_label(
        self, 
        pages: List[Dict],
        cluster_id: int
    ) -> Tuple[str, Dict]:
        # NOTE: This method is replaced below with a TF-IDF based approach.
        # It remains here only as a placeholder for backwards compatibility.
        return f"Topic {cluster_id + 1}", {"page_count": len(pages)}

    def _extract_words_from_text(self, text: str) -> List[str]:
        """
        Extract meaningful words from text.
        
        Args:
            text: Raw text content
            
        Returns:
            List of cleaned words (lowercase, 4+ chars, alphabetic only)
        """
        if not text:
            return []
        
        # Extract words: alphabetic only, 4-15 characters
        words = re.findall(r'\b[a-zA-Z]{4,15}\b', text.lower())
        
        # Basic filtering (minimal stop words - just the most obvious ones)
        basic_stops = {
            'this', 'that', 'with', 'from', 'have', 'been', 'were', 'they',
            'their', 'what', 'when', 'where', 'which', 'there', 'these', 'those',
            'will', 'would', 'could', 'should', 'about', 'into', 'than', 'then',
            'also', 'just', 'only', 'some', 'such', 'more', 'most', 'other',
            'being', 'does', 'doing', 'done', 'going', 'make', 'made', 'take',
            'took', 'come', 'came', 'want', 'said', 'each', 'even', 'after',
            'before', 'between', 'under', 'over', 'again', 'further', 'once'
        }
        
        return [w for w in words if w not in basic_stops]

    def _compute_tfidf_labels(
        self,
        clustered_pages: Dict[int, List[Dict]]
    ) -> Dict[int, Tuple[str, Dict]]:
        """
        Compute topic labels using sklearn's TfidfVectorizer.
        
        This version:
        1. Uses sklearn's robust TF-IDF implementation
        2. Filters web-specific noise (UI text, accessibility labels, etc.)
        3. Keeps only meaningful content words
        """
        from sklearn.feature_extraction.text import TfidfVectorizer
        from collections import Counter
        import numpy as np
        
        n_clusters = len(clustered_pages)
        
        # Web-specific noise words (UI elements, accessibility, boilerplate)
        web_noise_words = {
            # Pronouns and determiners (TF-IDF often misses these)
            'your', 'yours', 'yourself', 'yourselves',
            'their', 'theirs', 'themselves', 'itself', 'himself', 'herself',
            'myself', 'ourselves', 'anyone', 'everyone', 'someone', 'nobody',
            
            # UI and navigation
            'click', 'button', 'menu', 'navigation', 'navbar', 'sidebar',
            'header', 'footer', 'submit', 'cancel', 'close', 'open',
            'login', 'logout', 'signin', 'signup', 'register', 'subscribe',
            'download', 'upload', 'share', 'print', 'save', 'delete',
            'edit', 'update', 'refresh', 'reload', 'back', 'next', 'previous',
            'home', 'settings', 'profile', 'account', 'dashboard', 'admin',
            
            # Accessibility and screen readers
            'screen', 'reader', 'screenreader', 'accessible', 'accessibility',
            'skip', 'main', 'content', 'landmark', 'aria', 'role',
            'tabindex', 'focus', 'keyboard', 'navigate', 'navigation',
            
            # Forms and inputs
            'form', 'input', 'field', 'enter', 'type', 'select', 'choose',
            'option', 'checkbox', 'radio', 'dropdown', 'textarea',
            'required', 'optional', 'valid', 'invalid', 'error', 'success',
            'password', 'email', 'username', 'confirm', 'verify',
            
            # E-commerce and shopping (Amazon Rufus, etc.)
            'rufus', 'cart', 'checkout', 'shipping', 'delivery', 'order',
            'price', 'discount', 'coupon', 'promo', 'offer', 'deal',
            'wishlist', 'favorite', 'review', 'rating', 'stars',
            'seller', 'buyer', 'customer', 'support', 'help',
            
            # Feedback and engagement
            'feedback', 'survey', 'rate', 'rating', 'helpful', 'report',
            'flag', 'spam', 'abuse', 'comment', 'comments', 'reply',
            'like', 'dislike', 'upvote', 'downvote', 'vote', 'poll',
            
            # Cookies and privacy
            'cookie', 'cookies', 'privacy', 'policy', 'terms', 'conditions',
            'consent', 'accept', 'decline', 'preferences', 'gdpr', 'ccpa',
            
            # Time and dates
            'today', 'yesterday', 'tomorrow', 'week', 'month', 'year',
            'hour', 'minute', 'second', 'time', 'date', 'schedule',
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
            'january', 'february', 'march', 'april', 'june', 'july',
            'august', 'september', 'october', 'november', 'december',
            
            # Common but meaningless
            'please', 'thank', 'thanks', 'welcome', 'hello', 'sorry',
            'note', 'notice', 'warning', 'info', 'information', 'details',
            'more', 'less', 'show', 'hide', 'view', 'display', 'toggle',
            'free', 'premium', 'upgrade', 'trial', 'demo', 'beta',
            'version', 'release', 'latest', 'update', 'updates',
            
            # Generic tech terms (too common to be distinctive)
            'page', 'pages', 'site', 'website', 'link', 'links', 'click',
            'file', 'files', 'folder', 'document', 'image', 'video', 'audio',
            'text', 'font', 'size', 'color', 'style', 'format',
            
            # Actions too generic
            'getting', 'using', 'making', 'doing', 'going', 'coming',
            'looking', 'finding', 'trying', 'working', 'starting', 'ending',
        }
        
        # Step 1: Build corpus - one "document" per cluster
        cluster_documents = {}
        for cluster_id, pages in clustered_pages.items():
            # Combine content from all pages in this cluster
            texts = []
            for page in pages:
                # Get content (first 2000 chars to focus on main content)
                content = (page.get('content') or '')[:2000]
                
                # Also get title if it's not a domain
                title = page.get('title') or ''
                if title and '.' not in title:
                    texts.append(title)
                
                texts.append(content)
            
            cluster_documents[cluster_id] = ' '.join(texts)
        
        # Step 2: Use TfidfVectorizer with English stop words
        vectorizer = TfidfVectorizer(
            stop_words='english',  # Built-in English stop words
            max_features=500,      # Limit vocabulary
            min_df=1,              # Must appear in at least 1 cluster
            max_df=0.85,           # Ignore words in >85% of clusters
            ngram_range=(1, 1),    # Single words only
            token_pattern=r'\b[a-zA-Z]{4,15}\b',  # 4-15 char words only
            lowercase=True
        )
        
        # Fit on all cluster documents
        cluster_ids = sorted(cluster_documents.keys())
        corpus = [cluster_documents[cid] for cid in cluster_ids]
        
        try:
            tfidf_matrix = vectorizer.fit_transform(corpus)
            feature_names = vectorizer.get_feature_names_out()
        except ValueError as e:
            # Fallback if vectorizer fails (e.g., empty corpus)
            print(f"TF-IDF vectorizer failed: {e}")
            return self._fallback_labeling(clustered_pages)
        
        # Step 3: Extract top words for each cluster
        results = {}
        
        for idx, cluster_id in enumerate(cluster_ids):
            pages = clustered_pages[cluster_id]
            
            # Get TF-IDF scores for this cluster
            tfidf_scores = tfidf_matrix[idx].toarray().flatten()
            
            # Create word -> score mapping
            word_scores = {
                feature_names[i]: tfidf_scores[i] 
                for i in range(len(feature_names)) 
                if tfidf_scores[i] > 0
            }
            
            # Filter out web noise words
            word_scores = {
                word: score 
                for word, score in word_scores.items()
                if word.lower() not in web_noise_words
            }
            
            # Sort by score
            sorted_words = sorted(word_scores.items(), key=lambda x: x[1], reverse=True)
            
            # Get top words (with minimum score threshold)
            min_score = 0.05  # Minimum TF-IDF score to be considered
            top_words = [
                word for word, score in sorted_words 
                if score >= min_score
            ][:10]
            
            # Generate label
            if top_words:
                label_words = [w.capitalize() for w in top_words[:3]]
                label = " & ".join(label_words)
            else:
                # Fallback to domain-based
                label = self._generate_domain_based_label(pages, cluster_id)
            
            # Collect metadata
            domains = [p.get('domain', '') for p in pages if p.get('domain')]
            domain_counts = Counter(domains)
            
            metadata = {
                "page_count": len(pages),
                "top_words": top_words[:5],
                "top_words_tfidf": {
                    w: round(word_scores.get(w, 0), 4) 
                    for w in top_words[:5]
                },
                "top_domains": [d for d, c in domain_counts.most_common(3)],
                "sample_titles": [
                    (p.get('title') or p.get('domain', ''))[:80] 
                    for p in pages[:5]
                ],
                "sample_urls": [p.get('url', '') for p in pages[:5]],
                "label_method": "tfidf" if top_words else "domain_fallback"
            }
            
            results[cluster_id] = (label, metadata)
        
        return results

    def _fallback_labeling(self, clustered_pages: Dict[int, List[Dict]]) -> Dict[int, Tuple[str, Dict]]:
        """
        Fallback labeling when TF-IDF fails.
        Uses domain-based naming.
        """
        results = {}
        for cluster_id, pages in clustered_pages.items():
            label = self._generate_domain_based_label(pages, cluster_id)
            
            domains = [p.get('domain', '') for p in pages if p.get('domain')]
            domain_counts = Counter(domains)
            
            metadata = {
                "page_count": len(pages),
                "top_words": [],
                "top_domains": [d for d, c in domain_counts.most_common(3)],
                "sample_titles": [(p.get('title') or p.get('domain', ''))[:80] for p in pages[:5]],
                "sample_urls": [p.get('url', '') for p in pages[:5]],
                "label_method": "domain_fallback"
            }
            
            results[cluster_id] = (label, metadata)
        
        return results

    def _generate_domain_based_label(self, pages: List[Dict], cluster_id: int) -> str:
        """
        Generate a label based on domains when TF-IDF doesn't work.
        
        Args:
            pages: List of pages in this cluster
            cluster_id: Cluster ID for fallback
            
        Returns:
            A human-readable label
        """
        domains = [p.get('domain', '') for p in pages if p.get('domain')]
        
        if not domains:
            return f"Topic {cluster_id + 1}"
        
        domain_counts = Counter(domains)
        top_domain = domain_counts.most_common(1)[0][0]
        
        # Map common domains to friendly names
        domain_labels = {
            'github.com': 'Code & Development',
            'stackoverflow.com': 'Programming Q&A',
            'medium.com': 'Articles & Blogs',
            'arxiv.org': 'Research Papers',
            'youtube.com': 'Videos',
            'docs.google.com': 'Documents',
            'amazon': 'Shopping',
            'reddit.com': 'Discussions',
            'twitter.com': 'Social Media',
            'linkedin.com': 'Professional',
            'geeksforgeeks.org': 'Programming Tutorials',
            'w3schools.com': 'Web Tutorials',
            'wikipedia.org': 'Reference',
            'news': 'News',
        }
        
        for domain_pattern, label in domain_labels.items():
            if domain_pattern in top_domain.lower():
                return label
        
        # Clean domain for display
        clean_domain = top_domain.replace('www.', '').split('.')[0].capitalize()
        return f"Content from {clean_domain}"

    def _generate_topic_label(
        self, 
        pages: List[Dict],
        cluster_id: int
    ) -> Tuple[str, Dict]:
        """
        Generate label for a single cluster (backward compatibility).
        
        Note: For better results, use _compute_tfidf_labels() which considers
        all clusters together for TF-IDF calculation.
        """
        # This is a simplified version for single-cluster labeling
        # The full TF-IDF version needs all clusters
        
        if not pages:
            return f"Topic {cluster_id + 1}", {"page_count": 0}
        
        # Extract words from content
        all_words = []
        for page in pages:
            content = (page.get('content') or '')[:1000]
            all_words.extend(self._extract_words_from_text(content))
        
        word_counts = Counter(all_words)
        
        # Get most common words
        min_occurrences = max(2, len(pages) // 5)
        top_words = [
            word for word, count in word_counts.most_common(20)
            if count >= min_occurrences
        ][:5]
        
        if top_words:
            label = " & ".join([w.capitalize() for w in top_words[:3]])
        else:
            label = self._generate_domain_based_label(pages, cluster_id)
        
        # Domains
        domains = [p.get('domain', '') for p in pages if p.get('domain')]
        domain_counts = Counter(domains)
        
        metadata = {
            "page_count": len(pages),
            "top_words": top_words,
            "top_domains": [d for d, c in domain_counts.most_common(3)],
            "sample_titles": [(p.get('title') or p.get('domain', ''))[:80] for p in pages[:5]],
            "sample_urls": [p.get('url', '') for p in pages[:5]]
        }
        
        return label, metadata
    
    def train(
        self, 
        pages: List[Dict],
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Train the topic model on existing pages.
        
        This is the main training function that:
        1. Extracts embeddings from pages
        2. Preprocesses with scaling and PCA
        3. Finds optimal number of clusters using BIC
        4. Trains GMM with EM algorithm
        5. Generates topic labels
        
        Args:
            pages: List of page dictionaries. Each must have:
                   - 'embedding': List of 1024 floats
                   - 'title': Page title (for labeling)
                   - 'domain': Page domain (for labeling)
                   - 'id': Unique identifier
            
            force: If True, train even if already trained
        
        Returns:
            Dictionary with training results and topic information
        """
        # Check if we have enough pages
        valid_pages = [p for p in pages if p.get('embedding') is not None]
        
        if len(valid_pages) < self.min_pages_for_training:
            return {
                "success": False,
                "error": f"Need at least {self.min_pages_for_training} pages. Have {len(valid_pages)}.",
                "pages_available": len(valid_pages),
                "pages_required": self.min_pages_for_training
            }
        
        print(f"\n{'='*60}")
        print(f"TRAINING TOPIC MODEL")
        print(f"{'='*60}")
        print(f"Pages available: {len(valid_pages)}")
        
        # Step 1: Extract embeddings
        embeddings = [p['embedding'] for p in valid_pages]
        
        # Step 2: Preprocess (scale + PCA)
        print("\nStep 1: Preprocessing embeddings...")
        X = self._preprocess_embeddings(embeddings, fit=True)
        
        # Step 3: Find optimal number of clusters
        print("\nStep 2: Finding optimal cluster count...")
        self.n_clusters = self._find_optimal_clusters(X)
        
        # Step 4: Train final GMM
        print(f"\nStep 3: Training GMM with {self.n_clusters} clusters...")
        try:
            self.gmm = self._fit_gmm(X, self.n_clusters)
        except Exception as e:
            return {
                "success": False,
                "error": f"GMM training failed: {e}",
            }
        
        # Step 5: Assign pages to clusters
        print("\nStep 4: Assigning pages to clusters...")
        cluster_labels = self.gmm.predict(X)
        probabilities = self.gmm.predict_proba(X)
        log_densities = self.gmm.score_samples(X)

        # Build per-cluster density stats for confidence calibration.
        self.cluster_confidence_stats = {}
        for cluster_id in range(self.n_clusters):
            idxs = np.where(cluster_labels == cluster_id)[0]
            if len(idxs) == 0:
                continue
            vals = log_densities[idxs]
            self.cluster_confidence_stats[cluster_id] = {
                "min": float(np.min(vals)),
                "max": float(np.max(vals)),
                "p05": float(np.percentile(vals, 5)),
                "p10": float(np.percentile(vals, 10)),
                "p90": float(np.percentile(vals, 90)),
                "p95": float(np.percentile(vals, 95)),
            }
        
        # Group pages by cluster
        clustered_pages = {i: [] for i in range(self.n_clusters)}
        for idx, (page, label, probs) in enumerate(zip(valid_pages, cluster_labels, probabilities)):
            page_with_cluster = {
                **page,
                'cluster_id': int(label),
                'cluster_probability': float(probs[label]),
                'all_probabilities': [float(p) for p in probs]
            }
            clustered_pages[label].append(page_with_cluster)
        
        # Step 6: Generate topic labels using TF-IDF
        print("\nStep 5: Generating topic labels (using TF-IDF)...")

        # Use TF-IDF based labeling which considers all clusters together
        tfidf_results = self._compute_tfidf_labels(clustered_pages)

        self.topic_labels = {}
        self.topic_metadata = {}

        for cluster_id in range(self.n_clusters):
            if cluster_id in tfidf_results:
                label, metadata = tfidf_results[cluster_id]
            else:
                label, metadata = f"Topic {cluster_id + 1}", {"page_count": 0}
            
            self.topic_labels[cluster_id] = label
            self.topic_metadata[cluster_id] = metadata
            print(f"  Topic {cluster_id}: '{label}' ({metadata.get('page_count', 0)} pages)")
            if metadata.get('top_words_tfidf'):
                print(f"    TF-IDF scores: {metadata['top_words_tfidf']}")
        
        # Mark as trained
        self.is_trained = True
        self.training_timestamp = datetime.now()
        self.pages_at_training = len(valid_pages)
        
        # Clear outlier buffer after retraining
        self.outlier_buffer = []
        
        print(f"\n{'='*60}")
        print(f"TRAINING COMPLETE")
        print(f"{'='*60}\n")
        
        # Return results
        return {
            "success": True,
            "n_clusters": self.n_clusters,
            "pages_trained": len(valid_pages),
            "topics": {
                cluster_id: {
                    "label": self.topic_labels[cluster_id],
                    **self.topic_metadata[cluster_id]
                }
                for cluster_id in range(self.n_clusters)
            },
            "training_timestamp": self.training_timestamp.isoformat(),
            "clustered_pages": clustered_pages
        }
    
    def classify(
        self, 
        page: Dict,
        handle_outlier: bool = True
    ) -> Dict[str, Any]:
        """
        Classify a single page into a topic.
        
        Args:
            page: Page dictionary with 'embedding' key
            handle_outlier: If True and page doesn't fit any cluster well,
                           add to outlier buffer for potential new cluster
        
        Returns:
            Classification result dictionary
        """
        if not self.is_trained:
            return {
                "success": False,
                "error": "Model not trained. Call train() first."
            }
        
        if page.get('embedding') is None:
            return {
                "success": False,
                "error": "Page has no embedding."
            }
        
        # Preprocess the single embedding
        X = self._preprocess_embeddings([page['embedding']], fit=False)
        
        # Get cluster probabilities
        probabilities = self.gmm.predict_proba(X)[0]
        predicted_cluster = int(np.argmax(probabilities))
        raw_probability = float(probabilities[predicted_cluster])
        log_density = float(self.gmm.score_samples(X)[0])
        confidence = self._calibrate_confidence(predicted_cluster, raw_probability, log_density)
        
        # Check if this is an outlier (doesn't fit any cluster well)
        is_outlier = raw_probability < self.outlier_threshold
        
        result = {
            "success": True,
            "predicted_topic_id": predicted_cluster,
            "predicted_topic_label": self.topic_labels.get(predicted_cluster, f"Topic {predicted_cluster}"),
            "confidence": confidence,
            "raw_probability": raw_probability,
            "is_outlier": is_outlier,
            "all_probabilities": {
                self.topic_labels.get(i, f"Topic {i}"): float(p) 
                for i, p in enumerate(probabilities)
            }
        }
        
        # Handle outlier
        if is_outlier and handle_outlier:
            self.outlier_buffer.append({
                "page": page,
                "timestamp": datetime.now().isoformat(),
                "best_probability": raw_probability
            })
            result["added_to_outlier_buffer"] = True
            result["outlier_buffer_size"] = len(self.outlier_buffer)
            
            # Check if we should trigger new cluster creation
            if len(self.outlier_buffer) >= self.outliers_for_new_cluster:
                result["should_retrain"] = True
                result["retrain_reason"] = f"Accumulated {len(self.outlier_buffer)} outliers"
        
        return result
    
    def classify_batch(self, pages: List[Dict]) -> List[Dict]:
        """
        Classify multiple pages at once (more efficient).
        
        Args:
            pages: List of page dictionaries with embeddings
        
        Returns:
            List of classification results
        """
        return [self.classify(page) for page in pages]
    
    def get_topics_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all discovered topics.
        
        Returns:
            Dictionary with topic information
        """
        if not self.is_trained:
            return {
                "is_trained": False,
                "error": "Model not trained"
            }
        
        return {
            "is_trained": True,
            "n_topics": self.n_clusters,
            "training_timestamp": self.training_timestamp.isoformat() if self.training_timestamp else None,
            "pages_at_training": self.pages_at_training,
            "outlier_buffer_size": len(self.outlier_buffer),
            "topics": {
                cluster_id: {
                    "label": self.topic_labels[cluster_id],
                    **self.topic_metadata[cluster_id]
                }
                for cluster_id in range(self.n_clusters)
            }
        }
    
    def should_retrain(self, current_page_count: int) -> Tuple[bool, str]:
        """
        Check if we should retrain the model.
        
        Retrain triggers:
        1. Too many outliers accumulated
        2. Significant new pages since last training (>50% growth)
        3. Never trained before
        
        Args:
            current_page_count: Current total number of pages
        
        Returns:
            Tuple of (should_retrain: bool, reason: str)
        """
        if not self.is_trained:
            if current_page_count >= self.min_pages_for_training:
                return True, "Initial training needed"
            else:
                return False, f"Need {self.min_pages_for_training} pages, have {current_page_count}"
        
        # Check outlier buffer
        if len(self.outlier_buffer) >= self.outliers_for_new_cluster:
            return True, f"Accumulated {len(self.outlier_buffer)} outlier pages"
        
        # Check page growth
        growth = current_page_count - self.pages_at_training
        growth_ratio = growth / self.pages_at_training if self.pages_at_training > 0 else 0
        
        if growth_ratio > 0.5:  # More than 50% growth
            return True, f"Significant growth: {growth} new pages ({growth_ratio:.0%} increase)"
        
        return False, "No retrain needed"
    
    def save_model(self, user_id: str = "default") -> str:
        """
        Save the trained model to disk.
        
        Args:
            user_id: Identifier for the user (for multi-user support)
        
        Returns:
            Path to saved model file
        """
        if not self.is_trained:
            raise ValueError("Cannot save untrained model")
        
        model_data = {
            "pca": self.pca,
            "scaler": self.scaler,
            "gmm": self.gmm,
            "n_clusters": self.n_clusters,
            "topic_labels": self.topic_labels,
            "topic_metadata": self.topic_metadata,
            "cluster_confidence_stats": self.cluster_confidence_stats,
            "training_timestamp": self.training_timestamp.isoformat(),
            "pages_at_training": self.pages_at_training,
            "outlier_buffer": self.outlier_buffer,
            "config": {
                "n_components_pca": self.n_components_pca,
                "min_clusters": self.min_clusters,
                "max_clusters": self.max_clusters,
                "outlier_threshold": self.outlier_threshold
            }
        }
        
        filepath = os.path.join(self.model_save_path, f"topic_model_{user_id}.pkl")
        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)
        
        print(f"Model saved to {filepath}")
        return filepath
    
    def load_model(self, user_id: str = "default") -> bool:
        """
        Load a previously trained model from disk.
        
        Args:
            user_id: Identifier for the user
        
        Returns:
            True if loaded successfully, False otherwise
        """
        filepath = os.path.join(self.model_save_path, f"topic_model_{user_id}.pkl")
        
        if not os.path.exists(filepath):
            print(f"No saved model found at {filepath}")
            return False
        
        try:
            with open(filepath, 'rb') as f:
                model_data = pickle.load(f)
            
            self.pca = model_data["pca"]
            self.scaler = model_data["scaler"]
            self.gmm = model_data["gmm"]
            self.n_clusters = model_data["n_clusters"]
            self.topic_labels = model_data["topic_labels"]
            self.topic_metadata = model_data["topic_metadata"]
            self.cluster_confidence_stats = model_data.get("cluster_confidence_stats", {})
            self.training_timestamp = datetime.fromisoformat(model_data["training_timestamp"])
            self.pages_at_training = model_data["pages_at_training"]
            self.outlier_buffer = model_data.get("outlier_buffer", [])
            self.is_trained = True
            
            print(f"Model loaded from {filepath}")
            print(f"  Clusters: {self.n_clusters}")
            print(f"  Trained on: {self.pages_at_training} pages")
            print(f"  Training date: {self.training_timestamp}")
            
            return True
            
        except Exception as e:
            print(f"Error loading model: {e}")
            return False


# ============================================================
# TOPIC SERVICE - High-level interface for the application
# ============================================================

class TopicService:
    """
    High-level service class that integrates TopicModel with the application.
    
    This provides a simple interface for:
    - Training on database pages
    - Classifying new pages
    - Getting organized page listings
    - Managing model lifecycle
    """
    
    def __init__(self, db_session_factory=None):
        """
        Initialize the Topic Service.
        
        Args:
            db_session_factory: SQLAlchemy session factory for database access
        """
        self.model = TopicModel()
        self.db_session_factory = db_session_factory
    
    def train_from_pages(self, pages: List[Dict]) -> Dict:
        """
        Train the topic model from a list of pages.
        
        Args:
            pages: List of page dictionaries with embeddings
        
        Returns:
            Training results
        """
        result = self.model.train(pages)
        
        if result["success"]:
            # Save the model after successful training
            self.model.save_model()
        
        return result
    
    def classify_page(self, page: Dict) -> Dict:
        """
        Classify a single page into a topic.
        
        Args:
            page: Page dictionary with embedding
        
        Returns:
            Classification result
        """
        # Try to load model if not trained
        if not self.model.is_trained:
            self.model.load_model()
        
        return self.model.classify(page)
    
    def get_pages_by_topic(self, pages: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Organize pages by their predicted topics.
        
        Args:
            pages: List of all pages with embeddings
        
        Returns:
            Dictionary mapping topic labels to lists of pages
        """
        if not self.model.is_trained:
            self.model.load_model()
        
        if not self.model.is_trained:
            return {"Uncategorized": pages}
        
        organized = {}
        outliers = []
        
        for page in pages:
            if page.get('embedding') is None:
                outliers.append(page)
                continue
            
            result = self.model.classify(page, handle_outlier=False)
            
            if result["success"]:
                topic_label = result["predicted_topic_label"]
                
                if result["is_outlier"]:
                    topic_label = "Uncategorized"
                
                if topic_label not in organized:
                    organized[topic_label] = []
                
                page_with_info = {
                    **page,
                    "topic_confidence": result["confidence"],
                    "is_outlier": result["is_outlier"]
                }
                organized[topic_label].append(page_with_info)
            else:
                outliers.append(page)
        
        if outliers:
            organized["Uncategorized"] = outliers
        
        return organized
    
    def get_model_status(self) -> Dict:
        """Get the current status of the topic model."""
        return self.model.get_topics_summary()
    
    def check_and_retrain(self, pages: List[Dict]) -> Dict:
        """
        Check if retraining is needed and do it if so.
        
        Args:
            pages: All current pages
        
        Returns:
            Status dictionary
        """
        should_retrain, reason = self.model.should_retrain(len(pages))
        
        if should_retrain:
            print(f"Retraining triggered: {reason}")
            return self.train_from_pages(pages)
        
        return {
            "retrained": False,
            "reason": reason
        }
