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


3) it is possible to upload the same file twice

4) Update Embedding Upload in Elastic to add "metadata = {}" => to be able to access other fiels like "pages, ..."