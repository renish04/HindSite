import cohere
import os
from dotenv import load_dotenv

load_dotenv()


class CohereEmbedder:
    def __init__(self):
        self.client = cohere.Client(os.getenv("COHERE_API_KEY"))
        self.model = "embed-english-v3.0"

    def generate_document_embedding(self, text: str) -> list:
        """Generate embedding for a document/page. Uses 'search_document' input type."""
        text = text[:8000]  # Cohere's limit

        response = self.client.embed(
            texts=[text],
            model=self.model,
            input_type="search_document",
        )
        return response.embeddings[0]

    def generate_query_embedding(self, query: str) -> list:
        """Generate embedding for a search query. Uses 'search_query' input type."""
        query = query[:8000]
        response = self.client.embed(
            texts=[query],
            model=self.model,
            input_type="search_query",
        )
        return response.embeddings[0]


# Singleton instance
embedder = CohereEmbedder()
