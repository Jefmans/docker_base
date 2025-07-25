# from langchain.vectorstores import ElasticsearchStore
from langchain_community.vectorstores import ElasticsearchStore
# from langchain.embeddings import OpenAIEmbeddings
from langchain_community.embeddings import OpenAIEmbeddings
from elasticsearch import Elasticsearch
import os

def get_vectorstore(index_name: str = "pdf_chunks") -> ElasticsearchStore:
    es_client = Elasticsearch(os.environ.get("ELASTIC_HOST", "http://elasticsearch:9200")
        # basic_auth=(
        #     os.environ.get("ELASTIC_USER", ""),
        #     os.environ.get("ELASTIC_PASSWORD", "")
        # ),
        # verify_certs=False
    )

    embedding_model = OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_key=os.getenv("OPENAI_API_KEY"),
            )

    return ElasticsearchStore(
        index_name=index_name,
        embedding=embedding_model,
        es_connection=es_client
    )
