# from langchain.vectorstores import ElasticsearchStore
from langchain_community.vectorstores import ElasticsearchStore
# from langchain.embeddings import OpenAIEmbeddings
from langchain_community.embeddings import OpenAIEmbeddings
from elasticsearch import Elasticsearch
import os

def get_vectorstore(index_name: str = "pdf_chunks") -> ElasticsearchStore:
    es_client = Elasticsearch(
        hosts=[os.environ.get("ELASTIC_HOST", "http://elasticsearch:9200")],
        # basic_auth=(
        #     os.environ.get("ELASTIC_USER", ""),
        #     os.environ.get("ELASTIC_PASSWORD", "")
        # ),
        # verify_certs=False
    )

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    return ElasticsearchStore(
        index_name=index_name,
        embedding=embeddings,
        es_connection=es_client
    )
