/**
 * TopicView Component
 * 
 * Displays pages organized by AI-discovered topics.
 * Features:
 * - Topic cards showing each topic with page count
 * - Expandable topic sections to view pages
 * - Train/Retrain button
 * - Status indicator showing model state
 */

import React, { useState, useEffect } from 'react';
import './TopicView.css';

const API_BASE = 'http://localhost:8000';

// Topic Card Component
const TopicCard = ({ topic, isExpanded, onToggle, onPageClick }) => {
  const getTopicIcon = (label) => {
    // Simple icon mapping based on common words
    const labelLower = label.toLowerCase();
    if (labelLower.includes('machine') || labelLower.includes('learning') || labelLower.includes('ai')) return '🤖';
    if (labelLower.includes('web') || labelLower.includes('react') || labelLower.includes('javascript')) return '💻';
    if (labelLower.includes('python') || labelLower.includes('programming')) return '🐍';
    if (labelLower.includes('news')) return '📰';
    if (labelLower.includes('research') || labelLower.includes('paper')) return '📚';
    if (labelLower.includes('video') || labelLower.includes('youtube')) return '🎬';
    if (labelLower.includes('shop') || labelLower.includes('product')) return '🛒';
    if (labelLower.includes('uncategorized')) return '📁';
    return '📂';
  };

  return (
    <div className={`topic-card ${isExpanded ? 'expanded' : ''}`}>
      <div className="topic-header" onClick={onToggle}>
        <span className="topic-icon">{getTopicIcon(topic.topic_label)}</span>
        <div className="topic-info">
          <h3 className="topic-label">{topic.topic_label}</h3>
          <span className="topic-count">{topic.page_count} pages</span>
        </div>
        <span className="expand-arrow">{isExpanded ? '▼' : '▶'}</span>
      </div>
      
      {isExpanded && (
        <div className="topic-pages">
          {topic.pages.map((page) => (
            <div 
              key={page.id} 
              className={`page-item ${page.is_outlier ? 'outlier' : ''}`}
              onClick={() => onPageClick(page.url)}
            >
              <div className="page-title">{page.title || 'Untitled'}</div>
              <div className="page-meta">
                <span className="page-domain">{page.domain}</span>
                <span className="page-confidence">
                  {(page.topic_confidence * 100).toFixed(0)}% match
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Status Badge Component
const StatusBadge = ({ status }) => {
  if (!status) return null;
  
  return (
    <div className={`status-badge ${status.is_trained ? 'trained' : 'untrained'}`}>
      {status.is_trained ? (
        <>
          <span className="status-dot green"></span>
          <span>{status.n_topics} topics discovered</span>
        </>
      ) : (
        <>
          <span className="status-dot yellow"></span>
          <span>Model not trained</span>
        </>
      )}
    </div>
  );
};

// Main TopicView Component
const TopicView = () => {
  const [topics, setTopics] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [training, setTraining] = useState(false);
  const [expandedTopic, setExpandedTopic] = useState(null);
  const [error, setError] = useState(null);

  // Fetch model status
  const fetchStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/topics/status`);
      const data = await response.json();
      setStatus(data);
    } catch (err) {
      console.error('Failed to fetch status:', err);
    }
  };

  // Fetch organized pages
  const fetchTopics = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/topics/pages`);
      const data = await response.json();
      setTopics(data);
    } catch (err) {
      setError('Failed to load topics. Make sure the backend is running.');
      console.error('Failed to fetch topics:', err);
    } finally {
      setLoading(false);
    }
  };

  // Train the model
  const trainModel = async (forceRetrain = false) => {
    setTraining(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/topics/train`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force_retrain: forceRetrain })
      });
      const data = await response.json();
      
      if (data.success) {
        // Refresh topics after training
        await fetchStatus();
        await fetchTopics();
      } else {
        setError(data.message || 'Training failed');
      }
    } catch (err) {
      setError('Training failed. Check the console for details.');
      console.error('Training failed:', err);
    } finally {
      setTraining(false);
    }
  };

  // Auto-organize (train if needed + organize)
  const autoOrganize = async () => {
    setTraining(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/topics/auto-organize`, {
        method: 'POST'
      });
      const data = await response.json();
      
      if (data.success) {
        await fetchStatus();
        await fetchTopics();
      } else {
        setError(data.message || 'Auto-organize failed');
      }
    } catch (err) {
      setError('Auto-organize failed. Check the console for details.');
      console.error('Auto-organize failed:', err);
    } finally {
      setTraining(false);
    }
  };

  // Handle page click - open in new tab
  const handlePageClick = (url) => {
    if (chrome?.tabs) {
      chrome.tabs.create({ url });
    } else {
      window.open(url, '_blank');
    }
  };

  // Initial load
  useEffect(() => {
    fetchStatus();
    fetchTopics();
  }, []);

  return (
    <div className="topic-view">
      <div className="topic-header-bar">
        <h2>📚 Your Topics</h2>
        <StatusBadge status={status} />
      </div>

      <div className="topic-actions">
        <button 
          className="action-btn primary"
          onClick={autoOrganize}
          disabled={training}
        >
          {training ? '⏳ Processing...' : '✨ Auto-Organize'}
        </button>
        
        <button 
          className="action-btn secondary"
          onClick={() => trainModel(true)}
          disabled={training}
        >
          🔄 Retrain
        </button>
      </div>

      {error && (
        <div className="error-message">
          ⚠️ {error}
        </div>
      )}

      {loading ? (
        <div className="loading">
          <div className="spinner"></div>
          <p>Loading your topics...</p>
        </div>
      ) : topics.length === 0 ? (
        <div className="empty-state">
          <p>📭 No pages captured yet.</p>
          <p>Start browsing and HindSite will automatically save pages you read.</p>
        </div>
      ) : (
        <div className="topics-list">
          {topics.map((topic, index) => (
            <TopicCard
              key={topic.topic_label}
              topic={topic}
              isExpanded={expandedTopic === index}
              onToggle={() => setExpandedTopic(expandedTopic === index ? null : index)}
              onPageClick={handlePageClick}
            />
          ))}
        </div>
      )}

      {status?.is_trained && (
        <div className="model-info">
          <small>
            Model trained on {status.pages_at_training} pages
            {status.training_timestamp && ` · ${new Date(status.training_timestamp).toLocaleDateString()}`}
          </small>
        </div>
      )}
    </div>
  );
};

export default TopicView;

