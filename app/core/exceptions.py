class TruthLensError(Exception):
    pass


class RetrievalError(TruthLensError):
    pass


class LLMError(TruthLensError):
    pass


class OllamaConnectionError(LLMError):
    pass


class OpenRouterError(LLMError):
    pass


class ConfigurationError(TruthLensError):
    pass


class FAISSIndexNotFoundError(RetrievalError):
    pass


class EmbeddingError(RetrievalError):
    pass
