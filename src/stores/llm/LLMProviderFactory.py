from .providers import LangChainCohereProvider, LangChainGroqProvider
from .LLMEnums import LLMEnums

class LLMProviderFactory:
    def __init__(self, config: dict):
        self.config = config
    
    def create(self, provider: str = LLMEnums.COHERE.value):
        if provider == LLMEnums.COHERE.value:
            return LangChainCohereProvider(
                api_key=self.config.COHERE_API_KEY,
                default_input_max_characters=self.config.DEFAULT_INPUT_MAX_CHARACTERS,
                default_generation_max_output_tokens=self.config.DEFAULT_GENERATION_MAX_OUTPUT_TOKENS,
                default_generation_temperature=self.config.DEFAULT_GENERATION_TEMPERATURE
            )
        elif provider == LLMEnums.GROQ.value:
            return LangChainGroqProvider(
                api_key=getattr(self.config, "GROQ_API_KEY", ""),
                default_input_max_characters=self.config.DEFAULT_INPUT_MAX_CHARACTERS,
                default_generation_max_output_tokens=self.config.DEFAULT_GENERATION_MAX_OUTPUT_TOKENS,
                default_generation_temperature=self.config.DEFAULT_GENERATION_TEMPERATURE
            )
            
            
        
