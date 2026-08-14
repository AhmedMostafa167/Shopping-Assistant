from ..LLMInterface import LLMInterface
from ..LLMEnums import CoHereEnums
import cohere
import logging
import time


class CoHereProvider(LLMInterface):
    def __init__(self, api_key: str,
                       default_input_max_characters: int=1000,
                       default_generation_max_output_tokens: int=1000,
                       default_generation_temperature: float=0.1):

        self.api_key = api_key

        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature

        self.generation_model_id = None
        self.reranking_model_id = None
        self.embedding_model_id = None
        self.embedding_size = None

        self.client = cohere.ClientV2(api_key=self.api_key)

        self.logger = logging.getLogger(__name__)
        
    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id
        
    def set_embedding_model(self, model_id, embedding_size):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size
        
    def set_reranking_model(self, model_id):
        self.reranking_model_id = model_id
        
    def generate_text(self, prompt: str, chat_history: list=[], max_output_tokens: int=None,
                            temperature: float = None):

        if not self.client:
            self.logger.error("CoHere client was not set")
            return None

        if not self.generation_model_id:
            self.logger.error("Generation model for CoHere was not set")
            return None
        
        max_output_tokens = max_output_tokens if max_output_tokens else self.default_generation_max_output_tokens
        temperature = temperature if temperature else self.default_generation_temperature

        response = self.client.chat(
            model = self.generation_model_id,
            chat_history = chat_history,
            message = self.process_text(prompt),
            temperature = temperature,
            max_tokens = max_output_tokens
        )

        if not response or not response.text:
            self.logger.error("Error while generating text with CoHere")
            return None
        
        return response.text    
    
    def process_text(self, text: str):
        return text[:self.default_input_max_characters].strip()
    

    import time

    def embed_texts(self, texts: list, document_type: str = None, batch_size: int = 96, max_retries: int = 5):
        if not self.client:
            self.logger.error("CoHere client was not set")
            return None

        if not self.embedding_model_id:
            self.logger.error("Embedding model for CoHere was not set")
            return None

        input_type = CoHereEnums.DOCUMENT.value
        if document_type == CoHereEnums.QUERY.value:
            input_type = CoHereEnums.QUERY.value

        all_embeddings = []

        for batch_num, i in enumerate(range(0, len(texts), batch_size)):
            batch = texts[i:i + batch_size]
            attempt=0
            response = None
            while attempt <= max_retries:
                try:
                    response = self.client.embed(
                        model=self.embedding_model_id,
                        texts=batch,
                        input_type=input_type,
                        output_dimension=1024,
                        embedding_types=['float']
                    )
                    break
                except cohere.errors.TooManyRequestsError:
                    attempt +=1
                    wait = 60
                    self.logger.warning(
                        f"Rate limited on batch {batch_num}, waiting {wait}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait)
            else:
                self.logger.error(f"Batch {batch_num} failed after {max_retries} retries due to rate limiting")
                return None

            if not response or not response.embeddings or not response.embeddings.float:
                self.logger.error("Error while embedding text with CoHere")
                return None

            all_embeddings.extend(response.embeddings.float)
            self.logger.info(f"embedded {len(all_embeddings)}")
        return all_embeddings
    async def rerank(self, retrieved_products: list, query: str):
        if not self.client:
            self.logger.error("CoHere client was not set")
            return None
        if not self.reranking_model_id:
            self.logger.error("Reranking model for CoHere was not set")
            return None
        
        response = self.client.rerank(
            model = self.reranking_model_id,
            documents = retrieved_products,
            query = query
        )
        
        if not response or not response.results:
            self.logger.error("Error while reranking with CoHere")
            return None
        ranked_results = sorted(response.results, key=lambda x: x.relevance_score, reverse=True)

        return ranked_results