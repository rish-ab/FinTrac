from langchain_community.llms import OllamaLLM
from langchain_community.embeddings import OllamaEmbeddings
from src.config import settings

llm = OllamaLLM(
    model=settings.OLLAMA_MODEL,
    base_url=settings.OLLAMA_BASE_URL,
    temperature=0.1,        # low temp = more consistent financial output
    num_ctx=4096,           # context window — don't push higher on your RAM
)

embeddings = OllamaEmbeddings(
    model=settings.OLLAMA_EMBED_MODEL,
    base_url=settings.OLLAMA_BASE_URL,
)