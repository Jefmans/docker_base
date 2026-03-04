from collections.abc import Iterable

from elasticsearch import Elasticsearch


es = Elasticsearch("http://elasticsearch:9200")


def build_filter_clauses(filters: dict[str, object] | None) -> list[dict]:
    clauses: list[dict] = []
    if not filters:
        return clauses

    for field, value in filters.items():
        if value is None:
            continue

        if isinstance(value, str):
            if value:
                clauses.append({"term": {field: value}})
            continue

        if isinstance(value, Iterable):
            values = [item for item in value if item]
            if not values:
                continue
            if len(values) == 1:
                clauses.append({"term": {field: values[0]}})
            else:
                clauses.append({"terms": {field: values}})

    return clauses


def delete_by_filters(index_name: str, filters: dict[str, object] | None) -> int:
    clauses = build_filter_clauses(filters)
    if not clauses:
        return 0

    response = es.delete_by_query(
        index=index_name,
        query={"bool": {"filter": clauses}},
        conflicts="proceed",
        refresh=True,
        wait_for_completion=True,
    )
    return int(response.get("deleted", 0))
