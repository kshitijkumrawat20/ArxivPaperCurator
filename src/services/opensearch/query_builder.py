import logging 
from typing import Any, Dict, List, Optional 
logger = logging.getLogger(__name__)

class QueryBuilder: 
    """
    Query builder for arxiv papers search following refference pattern.
    Unified query builder for Opesearch supporting both paper-level and chunk-level search.
    
    """

    def __init__(
            self,
            query: str,
            size: int = 10, 
            from_: int = 0, 
            fields: Optional[List[str]] = None,
            categories: Optional[List[str]] = None,
            track_total_hits: bool = True,
            latest_papers: bool = False, 
            search_chunks: bool = False,
    ):
        """Initialize query builder.

        :param query: Search query text
        :param size: Number of results to return
        :param from_: Offset for pagination
        :param fields: Fields to search in (if None, auto-determined based on search_chunks)
        :param categories: Filter by categories
        :param track_total_hits: Whether to track total hits accurately
        :param latest_papers: Sort by publication date instead of relevance
        :param search_chunks: Whether to search chunk-level data
        """
        self.query = query
        self.size = size
        self.from_ = from_
        self.categories = categories
        self.track_total_hits = track_total_hits
        self.latest_papers = latest_papers
        self.search_chunks = search_chunks
        if fields is None: 
            if search_chunks: 
                self.fields = ["chunk_text^3", "section_name^2", "title^1", "abstract^1", "authors^1"]
            else:
                self.fields = ["title^3", "abstract^2", "authors^1"]
        else: 
            self.fields = fields

    def build(self) -> Dict[str,Any]: 
        """
        Build the complete OpenSearch query.
        returns : 
        :return: Dictionary representing the OpenSearch query
        """

        query_body = {
            "query": self._build_query(),
            "size": self.size,
            "from": self.from_,
            "track_total_hits": self.track_total_hits,
            "_source": self._build_source_fields(),
            "highlight": self._build_highlight()
        }

        # add sorting if need 
        sort = self._build_sort()
        if sort: 
            query_body["sort"] = sort
        
        return query_body
    
    def _build_query(self) -> Dict[str, Any]:
        """
        Build the main query with filters 
        :return: Dictionary representing the query
        """

        # Build must clauses for the main query
        must_clauses = []
        # main text search 
        if self.query.strip():
            must_clauses.append(self._build_text_query())
        
        # build filter clauses for categories if provided
        filter_clauses = self._build_filters()


        # contruct the bool query 
        bool_query = {}

        if must_clauses: 
            bool_query["must"] = must_clauses
        else: 
            # if no text query, match all document 
            bool_query["must"] = [{"match_all": {}}]
        
        if filter_clauses: 
            bool_query["filter"] = filter_clauses
        
        return {"bool": bool_query}
    
    def _build_text_query(self) -> Dict[str, Any]:
        """
        Build the main text search query. 
        :return: Dictionary representing the text search query
        """
        return {
            "multi_match": {
                "query": self.query,
                "fields": self.fields,
                "type": "best_fields",
                "operator": "or",
                "fuzziness": "AUTO",
                "prefix_length": 2
            }
        }
    
    def _build_filters(self) -> List[Dict[str, Any]]:
        """
            Build filter clauses for the query. 

            :return: List of filter clauses

        """
        filters = []

        # category filter 
        if self.categories:
            filters.append({
                "terms": {
                    "categories": self.categories
                }
            })
        return filters   
        
    def _build_source_fields(self) -> Any:
        """
        Specify which fields to return in the search results.
        :return: Source of fields configuration (list for papers, dict for chunsk ) """
        if self.search_chunks:
            return {
                "excludes": ["embedding"]  # Exclude embedding field for chunk-level search
            }
        else: 
            return ["arxiv_id", "title", "authors", "abstract", "categories", "published_date", "pdf_url"]
    
    def _build_highlight(self) -> Dict[str, Any]:
        """Build highlighting configuration.

        :returns: Highlight configuration dictionary
        """
        if self.search_chunks:
            return {
                "fields": {
                    "chunk_text": {
                        "fragment_size": 150,
                        "number_of_fragments": 2,
                        "pre_tags": ["<mark>"],
                        "post_tags": ["</mark>"],
                    },
                    "title": {"fragment_size": 0, "number_of_fragments": 0, "pre_tags": ["<mark>"], "post_tags": ["</mark>"]},
                    "abstract": {
                        "fragment_size": 150,
                        "number_of_fragments": 1,
                        "pre_tags": ["<mark>"],
                        "post_tags": ["</mark>"],
                    },
                },
                "require_field_match": False,
            }
        else:
            # Paper-specific highlighting
            return {
                "fields": {
                    "title": {
                        "fragment_size": 0,
                        "number_of_fragments": 0,
                    },
                    "abstract": {
                        "fragment_size": 150,
                        "number_of_fragments": 3,
                        "pre_tags": ["<mark>"],
                        "post_tags": ["</mark>"],
                    },
                    "authors": {
                        "fragment_size": 0,
                        "number_of_fragments": 0,
                        "pre_tags": ["<mark>"],
                        "post_tags": ["</mark>"],
                    },
                },
                "require_field_match": False,
            }
            
    
    def _build_sort(self) -> Optional[List[Dict[str, Any]]]:
        """Build sorting configuration.

        :returns: Sort configuration or None for relevance scoring
        """
        # If latest_papers is requested, always sort by publication date
        if self.latest_papers:
            return [{"published_date": {"order": "desc"}}, "_score"]

        # For text queries, use relevance scoring (no explicit sort)
        if self.query.strip():
            return None

        # For empty queries, sort by publication date (newest first)
        return [{"published_date": {"order": "desc"}}, "_score"]

    # def build_search_query(
    #     query: str,
    #     size: int = 10,
    #     from_: int = 0,
    #     categories: Optional[List[str]] = None,
    # ) -> Dict[str, Any]:
    #     """Helper function to build a search query with optional filters.

    #     :param query: Search query text
    #     :param size: Number of results
    #     :param from_: Offset for pagination
    #     :param categories: Optional filter by categories
    #     :returns: Search query dictionary
    #     """
    #     builder = QueryBuilder(query=query, size=size, from_=from_, categories=categories)
    #     return builder.build()


# # writing a test function to test the query builder
# def test_query_builder():
#     # Test case 1: Basic query with no filters
#     builder = PaperQueryBuilder(query="machine learning", size=5, from_=0)
#     query_body = builder.build()

#     assert "query" in query_body
#     assert query_body["size"] == 5
#     assert query_body["from"] == 0
#     assert "highlight" in query_body
#     print(query_body)

#     # Test case 2: Query with category filter
#     builder = PaperQueryBuilder(query="deep learning", size=10, from_=0, categories=["cs.LG"])
#     query_body = builder.build()
#     assert "query" in query_body
#     assert any("terms" in clause for clause in query_body["query"]["bool"].get("filter", []))
#     print(query_body)

#     # Test case 3: Empty query should match all documents
#     builder = PaperQueryBuilder(query="", size=10, from_=0)
#     query_body = builder.build()
#     assert "match_all" in query_body["query"]["bool"]["must"][0]
#     print(query_body)

#     print("All test cases passed!")


# # run the test function
# if __name__ == "__main__":
#     test_query_builder()
