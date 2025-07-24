uses "vector" field in es => because 
from langchain_elasticsearch import ElasticsearchStore
has no
vector_field="embedding"


TO DO 
-----

1) Save metadata list from images => PostgreSQL
        a. is in process in the backend


2) langchain-elasticsearch==0.1.3 => langchain-elasticsearch==0.3.2 + elasticsearch==9.x
        a. change embedding field name ??