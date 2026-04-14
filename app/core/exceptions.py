class SachError(Exception):
    pass


class RetrievalError(SachError):
    pass


class LLMError(SachError):
    pass


class OllamaConnectionError(LLMError):
    pass


class OpenRouterError(LLMError):
    pass


class ConfigurationError(SachError):
    pass


class FAISSIndexNotFoundError(RetrievalError):
    pass


class EmbeddingError(RetrievalError):
    pass
